#!/usr/bin/env python3
"""
对比 Google Maps Places API 与 google-maps-scraper 爬虫结果的测试用例。
支持三种匹配策略：精确名称、模糊名称、坐标距离。

运行前准备:
    1. 确保爬虫服务已启动: ./google-maps-scraper -web -data-folder ./webdata
    2. 设置环境变量: export GOOGLE_MAPS_API_KEY="your_api_key"
    3. 安装依赖: pip install requests

运行方式:
    python scripts/compare_test.py
"""

import json
import os
import random
import sys
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Dict, List, Optional, Set, Tuple

import requests


# ===================== 城市配置 =====================

CITIES = [
    {"name": "Cairo", "lat": 30.0444, "lng": 31.2357, "radius": 3000, "keywords": "hospital"},
    {"name": "Beijing", "lat": 39.9042, "lng": 116.4074, "radius": 3000, "keywords": "restaurant"},
    {"name": "New York", "lat": 40.7128, "lng": -74.0060, "radius": 3000, "keywords": "coffee shop"},
    {"name": "London", "lat": 51.5074, "lng": -0.1278, "radius": 3000, "keywords": "hotel"},
    {"name": "Tokyo", "lat": 35.6762, "lng": 139.6503, "radius": 3000, "keywords": "pharmacy"},
    {"name": "Paris", "lat": 48.8566, "lng": 2.3522, "radius": 3000, "keywords": "bakery"},
    {"name": "Sydney", "lat": -33.8688, "lng": 151.2093, "radius": 3000, "keywords": "cafe"},
    {"name": "Dubai", "lat": 25.2048, "lng": 55.2708, "radius": 3000, "keywords": "mall"},
    {"name": "Mumbai", "lat": 19.0760, "lng": 72.8777, "radius": 3000, "keywords": "bank"},
    {"name": "São Paulo", "lat": -23.5505, "lng": -46.6333, "radius": 3000, "keywords": "supermarket"},
]  # fmt: skip


def random_point_in_city(city: Dict[str, Any]) -> Tuple[float, float]:
    """在城市中心周围随机生成一个坐标点（均匀分布在半径范围内）"""
    center_lat = city["lat"]
    center_lng = city["lng"]
    radius_m = city["radius"]

    # 使用极坐标方法在圆内均匀随机取点
    # r = R * sqrt(random) 确保点在圆内均匀分布
    r = radius_m * sqrt(random.random())
    theta = random.uniform(0, 2 * 3.14159265359)

    # 1度纬度 ≈ 111,000 米
    # 1度经度 ≈ 111,000 * cos(纬度) 米
    lat_offset = r * cos(theta) / 111000.0
    lng_offset = r * sin(theta) / (111000.0 * cos(radians(center_lat)))

    return center_lat + lat_offset, center_lng + lng_offset


def pick_random_city() -> Dict[str, Any]:
    """随机选择一个城市配置"""
    return random.choice(CITIES)


# ===================== 数据模型 =====================


@dataclass
class SearchConfig:
    """搜索配置参数"""

    keywords: str
    lat: float
    lng: float
    radius: int
    lang: str = "zh-CN"
    zoom: int = 14


@dataclass
class POI:
    """兴趣点数据"""

    name: str
    lat: float
    lng: float
    address: str = ""
    phone: str = ""
    website: str = ""
    category: str = ""
    rating: float = 0.0

    def key(self) -> str:
        return self.name.strip().lower()


@dataclass
class MatchResult:
    """匹配结果统计"""

    strategy: str
    common_count: int
    only_gm_count: int
    only_sc_count: int
    match_rate: float
    avg_distance_m: float = 0.0
    max_distance_m: float = 0.0
    # 匹配的详情列表
    matches: List[Tuple[POI, POI, float]] = field(default_factory=list)
    # 仅 Google 的结果
    only_gm: List[POI] = field(default_factory=list)
    # 仅 Scraper 的结果
    only_sc: List[POI] = field(default_factory=list)


# ===================== 客户端 =====================


class GoogleMapsAPIClient:
    """Google Maps Places API (Nearby Search) 客户端"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

    def search(self, config: SearchConfig) -> List[POI]:
        pois: List[POI] = []
        next_page_token: Optional[str] = None
        page_count = 0

        while True:
            params = {
                "key": self.api_key,
                "location": f"{config.lat},{config.lng}",
                "radius": config.radius,
                "keyword": config.keywords,
                "language": config.lang,
            }
            if next_page_token:
                params["pagetoken"] = next_page_token

            resp = requests.get(self.base_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            status = data.get("status", "")
            if status not in ("OK", "ZERO_RESULTS"):
                raise RuntimeError(
                    f"Google Maps API error: {status} — {data.get('error_message', '')}"
                )

            for result in data.get("results", []):
                loc = result.get("geometry", {}).get("location", {})
                poi = POI(
                    name=result.get("name", ""),
                    lat=loc.get("lat", 0.0),
                    lng=loc.get("lng", 0.0),
                    address=result.get("vicinity", ""),
                    rating=result.get("rating", 0.0) or 0.0,
                )
                pois.append(poi)

            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break

            page_count += 1
            if page_count >= 2:
                break

            time.sleep(2)

        return pois


class ScraperClient:
    """google-maps-scraper 本地 API 客户端"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip("/")

    def _build_geojson(self, config: SearchConfig) -> str:
        geojson = {
            "type": "Feature",
            "properties": {"type": "circle", "radius": config.radius},
            "geometry": {
                "type": "Point",
                "coordinates": [config.lng, config.lat],
            },
        }
        return json.dumps(geojson)

    def submit_job(self, config: SearchConfig, job_name: str = "compare_test") -> str:
        payload = {
            "name": job_name,
            "keywords": [config.keywords],
            "lang": config.lang,
            "zoom": config.zoom,
            "lat": str(config.lat),
            "lon": str(config.lng),
            "geojson": self._build_geojson(config),
            "radius": config.radius,
            "fast_mode": False,
            "depth": 10,
            "max_time": 600,
            "email": False,
        }

        resp = requests.post(
            f"{self.base_url}/api/v1/jobs",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def get_job_status(self, job_id: str) -> Optional[str]:
        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/jobs/{job_id}",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("status") or data.get("Status")
        except Exception as e:
            print(f"[Scraper] 查询任务状态失败: {e}")
            return None

    def get_results(self, job_id: str) -> Optional[List[POI]]:
        resp = requests.get(
            f"{self.base_url}/api/v1/jobs/{job_id}/pois",
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, dict):
            pois_data = data.get("pois", [])
        else:
            pois_data = data

        if not pois_data:
            return None

        return [
            POI(
                name=p.get("name", ""),
                lat=p.get("lat", 0.0),
                lng=p.get("lng", 0.0),
                address=p.get("address", ""),
                phone=p.get("phone", ""),
                website=p.get("website", ""),
                category=p.get("category", ""),
                rating=p.get("rating", 0.0) or 0.0,
            )
            for p in pois_data
        ]

    def search(
        self,
        config: SearchConfig,
        poll_interval: int = 5,
        max_wait: int = 300,
    ) -> List[POI]:
        job_id = self.submit_job(config)
        print(f"[Scraper] 任务已提交: {job_id}")

        start = time.time()
        while time.time() - start < max_wait:
            status = self.get_job_status(job_id)
            print(f"[Scraper] 当前状态: {status} (已等待 {int(time.time()-start)}s)")

            if status == "ok":
                results = self.get_results(job_id)
                if results is not None:
                    return results
                print("[Scraper] 任务完成但暂无结果，继续等待 CSV 写入...")
            elif status == "failed":
                raise RuntimeError(f"爬虫任务执行失败: {job_id}")
            else:
                results = self.get_results(job_id)
                if results is not None:
                    print(f"[Scraper] 直接获取到结果，任务实际已完成")
                    return results

            time.sleep(poll_interval)

        raise TimeoutError(f"爬虫任务 {job_id} 在 {max_wait} 秒内未完成")


# ===================== 匹配算法 =====================


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两点间的大圆距离（米）"""
    R = 6371000
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlng / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def name_similarity(a: str, b: str) -> float:
    """计算两个名称的相似度 (0.0 ~ 1.0)"""
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def match_by_exact_name(gm_pois: List[POI], sc_pois: List[POI]) -> MatchResult:
    """A. 精确名称匹配"""
    gm_names = {p.key() for p in gm_pois}
    sc_names = {p.key() for p in sc_pois}

    common_names = gm_names & sc_names
    only_gm_names = gm_names - sc_names
    only_sc_names = sc_names - gm_names

    gm_dict = {p.key(): p for p in gm_pois}
    sc_dict = {p.key(): p for p in sc_pois}

    matches = []
    for name in common_names:
        gm = gm_dict[name]
        sc = sc_dict[name]
        dist = haversine(gm.lat, gm.lng, sc.lat, sc.lng)
        matches.append((gm, sc, dist))

    total = max(len(gm_names), len(sc_names))
    match_rate = len(common_names) / total * 100 if total > 0 else 0

    return MatchResult(
        strategy="精确名称匹配",
        common_count=len(common_names),
        only_gm_count=len(only_gm_names),
        only_sc_count=len(only_sc_names),
        match_rate=match_rate,
        avg_distance_m=sum(m[2] for m in matches) / len(matches) if matches else 0,
        max_distance_m=max((m[2] for m in matches), default=0),
        matches=matches,
        only_gm=[gm_dict[n] for n in only_gm_names],
        only_sc=[sc_dict[n] for n in only_sc_names],
    )


def match_by_fuzzy_name(
    gm_pois: List[POI], sc_pois: List[POI], threshold: float = 0.6
) -> MatchResult:
    """B. 模糊名称匹配（编辑距离）"""
    matched_sc_indices: Set[int] = set()
    matches: List[Tuple[POI, POI, float]] = []

    for gm in gm_pois:
        best_sim = 0.0
        best_idx = -1
        for idx, sc in enumerate(sc_pois):
            if idx in matched_sc_indices:
                continue
            sim = name_similarity(gm.name, sc.name)
            if sim > best_sim:
                best_sim = sim
                best_idx = idx

        if best_sim >= threshold and best_idx >= 0:
            sc = sc_pois[best_idx]
            dist = haversine(gm.lat, gm.lng, sc.lat, sc.lng)
            matches.append((gm, sc, dist))
            matched_sc_indices.add(best_idx)

    only_gm = [gm for gm in gm_pois if not any(m[0] == gm for m in matches)]
    only_sc = [sc for idx, sc in enumerate(sc_pois) if idx not in matched_sc_indices]

    total = max(len(gm_pois), len(sc_pois))
    match_rate = len(matches) / total * 100 if total > 0 else 0

    return MatchResult(
        strategy="模糊名称匹配",
        common_count=len(matches),
        only_gm_count=len(only_gm),
        only_sc_count=len(only_sc),
        match_rate=match_rate,
        avg_distance_m=sum(m[2] for m in matches) / len(matches) if matches else 0,
        max_distance_m=max((m[2] for m in matches), default=0),
        matches=matches,
        only_gm=only_gm,
        only_sc=only_sc,
    )


def match_by_distance(
    gm_pois: List[POI], sc_pois: List[POI], threshold_m: float = 100.0
) -> MatchResult:
    """C. 坐标距离匹配（最可靠的"同一地点"判断）"""
    matched_sc_indices: Set[int] = set()
    matches: List[Tuple[POI, POI, float]] = []

    for gm in gm_pois:
        best_dist = float("inf")
        best_idx = -1
        for idx, sc in enumerate(sc_pois):
            if idx in matched_sc_indices:
                continue
            dist = haversine(gm.lat, gm.lng, sc.lat, sc.lng)
            if dist < best_dist:
                best_dist = dist
                best_idx = idx

        if best_dist <= threshold_m and best_idx >= 0:
            sc = sc_pois[best_idx]
            matches.append((gm, sc, best_dist))
            matched_sc_indices.add(best_idx)

    only_gm = [gm for gm in gm_pois if not any(m[0] == gm for m in matches)]
    only_sc = [sc for idx, sc in enumerate(sc_pois) if idx not in matched_sc_indices]

    total = max(len(gm_pois), len(sc_pois))
    match_rate = len(matches) / total * 100 if total > 0 else 0

    return MatchResult(
        strategy="坐标距离匹配",
        common_count=len(matches),
        only_gm_count=len(only_gm),
        only_sc_count=len(only_sc),
        match_rate=match_rate,
        avg_distance_m=sum(m[2] for m in matches) / len(matches) if matches else 0,
        max_distance_m=max((m[2] for m in matches), default=0),
        matches=matches,
        only_gm=only_gm,
        only_sc=only_sc,
    )


# ===================== 报告输出 =====================


def print_match_result(result: MatchResult, verbose: bool = False):
    """打印某一种匹配策略的结果"""
    print(f"\n{'='*65}")
    print(f"🔍 {result.strategy}")
    print(f"{'='*65}")
    print(f"  共同结果        : {result.common_count} 个")
    print(f"  仅在 Google     : {result.only_gm_count} 个")
    print(f"  仅在 Scraper    : {result.only_sc_count} 个")
    print(f"  匹配率          : {result.match_rate:.1f} %")

    if result.matches:
        print(f"  平均坐标偏差    : {result.avg_distance_m:.1f} 米")
        print(f"  最大坐标偏差    : {result.max_distance_m:.1f} 米")

    if not verbose:
        return

    if result.only_gm:
        print(f"\n  仅在 Google Maps 中的结果 (前5):")
        for p in result.only_gm[:5]:
            print(f"    - {p.name}")

    if result.only_sc:
        print(f"\n  仅在 Scraper 中的结果 (前5):")
        for p in result.only_sc[:5]:
            print(f"    - {p.name}")

    if result.matches:
        print(f"\n  匹配样本详情 (按坐标偏差排序):")
        sorted_matches = sorted(result.matches, key=lambda x: x[2])
        for gm, sc, dist in sorted_matches[:3]:
            sim = name_similarity(gm.name, sc.name)
            print(f"    📍 {dist:.1f}m | 名称相似度 {sim:.0%}")
            print(f"       GM: {gm.name}")
            print(f"       SC: {sc.name}")


def print_summary(
    gm_pois: List[POI],
    sc_pois: List[POI],
    exact: MatchResult,
    fuzzy: MatchResult,
    dist: MatchResult,
):
    """打印综合对比报告"""
    print("\n" + "=" * 65)
    print("📊 综合对比总结")
    print("=" * 65)
    print(f"{'策略':<20} {'匹配数':>8} {'匹配率':>10} {'平均偏差':>12} {'最大偏差':>12}")
    print("-" * 65)
    for r in (exact, fuzzy, dist):
        print(
            f"{r.strategy:<20} {r.common_count:>8} {r.match_rate:>9.1f}% "
            f"{r.avg_distance_m:>10.1f}m {r.max_distance_m:>10.1f}m"
        )

    print(f"\n{'='*65}")
    print("📋 关键发现")
    print(f"{'='*65}")

    print(f"\n1. 结果数量差异")
    print(f"   Google Maps API: {len(gm_pois)} 个")
    print(f"   Scraper:         {len(sc_pois)} 个")
    print(f"   差异:            {len(sc_pois) - len(gm_pois):+d} 个")

    print(f"\n2. 名称匹配率低的原因")
    print(f"   • 同一地点在 API 和网页中可能使用不同语言/别名显示")
    print(f"   • API 返回标准化名称，网页返回用户可见名称")
    print(f"   • 精确名称匹配率: {exact.match_rate:.1f}%")
    print(f"   • 模糊名称匹配率: {fuzzy.match_rate:.1f}%")
    print(f"   • 坐标距离匹配率: {dist.match_rate:.1f}% ← 最可靠的'同一地点'判断")

    print(f"\n3. 数据质量评估")
    if dist.matches:
        avg_dist = dist.avg_distance_m
        if avg_dist < 10:
            quality = "优秀"
        elif avg_dist < 50:
            quality = "良好"
        elif avg_dist < 200:
            quality = "一般"
        else:
            quality = "较差"
        print(f"   • 坐标一致性: {quality} (平均偏差 {avg_dist:.1f} 米)")
    else:
        print(f"   • 未找到坐标匹配的地点")


def run_assertions(exact: MatchResult, fuzzy: MatchResult, dist: MatchResult):
    """运行断言检查"""
    print(f"\n{'='*65}")
    print("✅ 断言检查")
    print(f"{'='*65}")

    ok = True

    # 断言 1: 坐标距离匹配率应较高（>= 40%）
    if dist.match_rate < 40:
        print(f"  ❌ 坐标匹配率过低: {dist.match_rate:.1f}% (期望 ≥ 40%)")
        ok = False
    else:
        print(f"  ✅ 坐标匹配率: {dist.match_rate:.1f}%")

    # 断言 2: 模糊名称匹配率应高于精确匹配
    if fuzzy.match_rate < exact.match_rate:
        print(f"  ⚠️  模糊匹配率({fuzzy.match_rate:.1f}%) 低于精确匹配率({exact.match_rate:.1f}%)")
    else:
        print(f"  ✅ 模糊匹配率({fuzzy.match_rate:.1f}%) ≥ 精确匹配率({exact.match_rate:.1f}%)")

    # 断言 3: 匹配地点的平均坐标偏差应很小
    if dist.matches:
        if dist.avg_distance_m > 500:
            print(f"  ❌ 平均坐标偏差过大: {dist.avg_distance_m:.1f}米 (期望 ≤ 500米)")
            ok = False
        else:
            print(f"  ✅ 平均坐标偏差: {dist.avg_distance_m:.1f}米")

    # 断言 4: 爬虫至少返回一些结果
    if dist.common_count == 0 and fuzzy.common_count == 0:
        print(f"  ❌ 未找到任何匹配的 POI")
        ok = False
    else:
        print(f"  ✅ 找到匹配的 POI: 坐标{dist.common_count}个 / 模糊{fuzzy.common_count}个")

    return ok


# ===================== 主流程 =====================


def run_test(
    config: SearchConfig,
    google_key: str,
    scraper_url: str,
    verbose: bool = False,
) -> Tuple[List[POI], List[POI], MatchResult, MatchResult, MatchResult]:
    print("=" * 65)
    print("🧪 Google Maps API vs Scraper 对比测试")
    print("=" * 65)
    print(f"  关键词 : {config.keywords}")
    print(f"  中心   : ({config.lat}, {config.lng})")
    print(f"  半径   : {config.radius} 米")
    print(f"  语言   : {config.lang}")
    print(f"  匹配策略: 精确名称 / 模糊名称 / 坐标距离(≤100m)")
    if verbose:
        print(f"  模式   : 详细输出 (-v)")

    # 1) Google Maps API
    print("\n" + "-" * 65)
    print("🔎 步骤 1/2: 调用 Google Maps Places API ...")
    print("-" * 65)
    gm_client = GoogleMapsAPIClient(google_key)
    gm_pois = gm_client.search(config)
    print(f"✅ 获取到 {len(gm_pois)} 个 POI")

    # 2) Scraper
    print("\n" + "-" * 65)
    print("🕷️ 步骤 2/2: 调用 Scraper ...")
    print("-" * 65)
    scraper_client = ScraperClient(scraper_url)
    sc_pois = scraper_client.search(config)
    print(f"✅ 获取到 {len(sc_pois)} 个 POI")

    # 3) 三种匹配策略
    exact = match_by_exact_name(gm_pois, sc_pois)
    fuzzy = match_by_fuzzy_name(gm_pois, sc_pois, threshold=0.6)
    dist = match_by_distance(gm_pois, sc_pois, threshold_m=100.0)

    print_match_result(exact, verbose=verbose)
    print_match_result(fuzzy, verbose=verbose)
    print_match_result(dist, verbose=verbose)

    print_summary(gm_pois, sc_pois, exact, fuzzy, dist)

    return gm_pois, sc_pois, exact, fuzzy, dist


def main():
    GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    SCRAPER_BASE_URL = os.environ.get("SCRAPER_URL", "http://localhost:8080")
    verbose = "-v" in sys.argv or "--verbose" in sys.argv

    if not GOOGLE_MAPS_API_KEY:
        print("错误: 请设置环境变量 GOOGLE_MAPS_API_KEY")
        print("  export GOOGLE_MAPS_API_KEY='your_api_key'")
        sys.exit(1)

    # 随机选择城市并在其周边生成随机坐标
    city = pick_random_city()
    rand_lat, rand_lng = random_point_in_city(city)

    test_config = SearchConfig(
        keywords=city["keywords"],
        lat=round(rand_lat, 6),
        lng=round(rand_lng, 6),
        radius=city["radius"],
        lang="en",
        zoom=14,
    )

    print(f"\n🌍 随机选择城市: {city['name']}")
    print(f"   中心坐标: ({city['lat']}, {city['lng']})")
    print(f"   测试坐标: ({test_config.lat}, {test_config.lng})")
    print(f"   搜索半径: {city['radius']} 米")

    gm_pois, sc_pois, exact, fuzzy, dist = run_test(
        test_config, GOOGLE_MAPS_API_KEY, SCRAPER_BASE_URL, verbose=verbose
    )

    ok = run_assertions(exact, fuzzy, dist)

    if not ok:
        print("\n⚠️ 部分断言未通过，请检查差异详情。")
        print("  使用 -v 参数查看详细列表: python scripts/compare_test.py -v")
        sys.exit(1)

    print("\n🎉 测试全部通过！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
