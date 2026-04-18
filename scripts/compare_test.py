#!/usr/bin/env python3
"""

google maps key:AIzaSyDyoj6rRSqmFF20-F89cKhditWELSIXr-I

对比 Google Maps Places API 与 google-maps-scraper 爬虫结果的测试用例。

运行前准备:
    1. 确保爬虫服务已启动: ./google-maps-scraper -web -data-folder ./webdata
    2. 设置环境变量: export GOOGLE_MAPS_API_KEY="AIzaSyDyoj6rRSqmFF20-F89cKhditWELSIXr-I"
    3. 安装依赖: pip install requests

运行方式:
    python scripts/compare_test.py
"""

import json
import os
import sys
import time
from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Dict, List, Optional, Set

import requests


# ===================== 数据模型 =====================


@dataclass
class SearchConfig:
    """搜索配置参数"""

    keywords: str  # 搜索关键词，如 "hospital"
    lat: float  # 中心纬度
    lng: float  # 中心经度
    radius: int  # 搜索半径（米）
    lang: str = "zh-CN"  # 结果语言
    zoom: int = 14  # 地图层级


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
        """用于匹配的标准化键"""
        return self.name.strip().lower()


# ===================== 客户端 =====================


class GoogleMapsAPIClient:
    """Google Maps Places API (Nearby Search) 客户端"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

    def search(self, config: SearchConfig) -> List[POI]:
        """
        使用 Nearby Search API 搜索 POI。
        Google Maps API 每页最多返回 60 个结果（3页）。
        """
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
            if page_count >= 2:  # 最多 3 页 (0,1,2)
                break

            # Google 要求等待 page token 生效
            time.sleep(2)

        return pois


class ScraperClient:
    """google-maps-scraper 本地 API 客户端"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip("/")

    def _build_geojson(self, config: SearchConfig) -> str:
        """根据中心点和半径构建圆形 GeoJSON"""
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
        """提交爬虫任务，返回 job_id"""
        payload = {
            "name": job_name,
            "keywords": [config.keywords],
            "lang": config.lang,
            "zoom": config.zoom,
            "lat": str(config.lat),
            "lon": str(config.lng),
            "geojson": self._build_geojson(config),
            "radius": config.radius,
            "fast_mode": True,
            "depth": 1,
            "max_time": 180,  # 秒，API 层会转换为 duration
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
        """获取任务状态: pending / working / ok / failed / None(查询失败)"""
        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/jobs/{job_id}",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            # Go 后端序列化字段名为大写，兼容大小写
            return data.get("status") or data.get("Status")
        except Exception as e:
            print(f"[Scraper] 查询任务状态失败: {e}")
            return None

    def get_results(self, job_id: str) -> Optional[List[POI]]:
        """
        获取任务结果。
        如果任务未完成返回 None；如果已完成但无结果返回 []。
        """
        resp = requests.get(
            f"{self.base_url}/api/v1/jobs/{job_id}/pois",
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # 新格式: {pois: [...], query_area: {...}, name, keywords, lang}
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
        """
        完整搜索流程：提交任务 -> 轮询状态 -> 获取结果。
        如果任务失败或无结果会抛出异常。
        """
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
                # 状态未知时，也尝试直接获取结果（任务可能已完成）
                results = self.get_results(job_id)
                if results is not None:
                    print(f"[Scraper] 直接获取到结果，任务实际已完成")
                    return results

            time.sleep(poll_interval)

        raise TimeoutError(f"爬虫任务 {job_id} 在 {max_wait} 秒内未完成")


# ===================== 对比分析 =====================


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两点间的大圆距离（米）"""
    R = 6371000  # 地球半径（米）
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlng / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def analyze_name_match(gm_pois: List[POI], scraper_pois: List[POI]) -> Dict[str, Any]:
    """名称匹配分析"""
    gm_names: Set[str] = {p.key() for p in gm_pois}
    sc_names: Set[str] = {p.key() for p in scraper_pois}

    common = gm_names & sc_names
    only_gm = gm_names - sc_names
    only_sc = sc_names - gm_names

    total = max(len(gm_names), len(sc_names))
    match_rate = len(common) / total * 100 if total > 0 else 0

    return {
        "common_count": len(common),
        "only_gm_count": len(only_gm),
        "only_sc_count": len(only_sc),
        "match_rate": match_rate,
        "common_names": common,
        "only_gm_names": only_gm,
        "only_sc_names": only_sc,
    }


def analyze_coordinate_diff(
    gm_pois: List[POI], scraper_pois: List[POI], common_names: Set[str]
) -> Dict[str, Any]:
    """坐标差异分析（仅针对名称匹配的 POI）"""
    gm_dict = {p.key(): p for p in gm_pois}
    sc_dict = {p.key(): p for p in scraper_pois}

    distances: List[tuple] = []
    for name in common_names:
        gm = gm_dict[name]
        sc = sc_dict[name]
        dist = haversine(gm.lat, gm.lng, sc.lat, sc.lng)
        distances.append((name, dist, gm, sc))

    distances.sort(key=lambda x: x[1], reverse=True)

    avg_dist = sum(d[1] for d in distances) / len(distances) if distances else 0
    max_dist = distances[0][1] if distances else 0

    return {
        "sample_count": len(distances),
        "avg_distance_m": avg_dist,
        "max_distance_m": max_dist,
        "top_differences": distances[:5],
    }


def compare_results(gm_pois: List[POI], scraper_pois: List[POI]) -> Dict[str, Any]:
    """全面对比两组结果并打印报告"""
    print("\n" + "=" * 65)
    print("📊 一、结果数量对比")
    print("=" * 65)
    print(f"  Google Maps API : {len(gm_pois):3d} 个")
    print(f"  Scraper         : {len(scraper_pois):3d} 个")
    print(f"  差异            : {len(scraper_pois) - len(gm_pois):+3d} 个")

    # 名称匹配
    name_analysis = analyze_name_match(gm_pois, scraper_pois)
    print("\n" + "=" * 65)
    print("🔍 二、名称匹配分析")
    print("=" * 65)
    print(f"  共同结果        : {name_analysis['common_count']} 个")
    print(f"  仅在 Google     : {name_analysis['only_gm_count']} 个")
    print(f"  仅在 Scraper    : {name_analysis['only_sc_count']} 个")
    print(f"  名称匹配率      : {name_analysis['match_rate']:.1f} %")

    if name_analysis["only_gm_names"]:
        print(f"\n  仅在 Google Maps 中的结果 (前10):")
        for n in list(name_analysis["only_gm_names"])[:10]:
            print(f"    - {n}")

    if name_analysis["only_sc_names"]:
        print(f"\n  仅在 Scraper 中的结果 (前10):")
        for n in list(name_analysis["only_sc_names"])[:10]:
            print(f"    - {n}")

    # 坐标差异
    coord_analysis = analyze_coordinate_diff(
        gm_pois, scraper_pois, name_analysis["common_names"]
    )
    print("\n" + "=" * 65)
    print("📍 三、坐标差异分析（名称匹配样本）")
    print("=" * 65)
    print(f"  可比对样本数    : {coord_analysis['sample_count']} 个")
    print(f"  平均偏差        : {coord_analysis['avg_distance_m']:.1f} 米")
    print(f"  最大偏差        : {coord_analysis['max_distance_m']:.1f} 米")

    if coord_analysis["top_differences"]:
        print(f"\n  偏差最大的 5 个样本:")
        for name, dist, gm, sc in coord_analysis["top_differences"]:
            print(f"    - {name}: {dist:.1f}m")
            print(
                f"        GM: ({gm.lat:.6f}, {gm.lng:.6f})  "
                f"SC: ({sc.lat:.6f}, {sc.lng:.6f})"
            )

    return {
        "google_count": len(gm_pois),
        "scraper_count": len(scraper_pois),
        **name_analysis,
        **coord_analysis,
    }


# ===================== 主流程 =====================


def run_test(config: SearchConfig, google_key: str, scraper_url: str) -> Dict[str, Any]:
    """执行一次完整对比测试"""
    print("=" * 65)
    print("🧪 Google Maps API vs Scraper 对比测试")
    print("=" * 65)
    print(f"  关键词 : {config.keywords}")
    print(f"  中心   : ({config.lat}, {config.lng})")
    print(f"  半径   : {config.radius} 米")
    print(f"  语言   : {config.lang}")

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
    scraper_pois = scraper_client.search(config)
    print(f"✅ 获取到 {len(scraper_pois)} 个 POI")

    # 3) 对比
    return compare_results(gm_pois, scraper_pois)


def main():
    # ----------- 配置区 -----------
    GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    SCRAPER_BASE_URL = os.environ.get("SCRAPER_URL", "http://localhost:8080")

    if not GOOGLE_MAPS_API_KEY:
        print("错误: 请设置环境变量 GOOGLE_MAPS_API_KEY")
        print("  export GOOGLE_MAPS_API_KEY='your_api_key'")
        sys.exit(1)

    # 使用与之前 Cairo Hospital 任务相同的查询条件
    test_config = SearchConfig(
        keywords="hospital",
        lat=30.035829,
        lng=31.228015,
        radius=1777,
        lang="en",
        zoom=14,
    )

    # 执行测试
    results = run_test(test_config, GOOGLE_MAPS_API_KEY, SCRAPER_BASE_URL)

    # 断言检查（可根据业务需求调整阈值）
    print("\n" + "=" * 65)
    print("✅ 断言检查")
    print("=" * 65)

    ok = True

    if results["match_rate"] < 20:
        print(f"  ❌ 名称匹配率过低: {results['match_rate']:.1f}% (期望 ≥ 20%)")
        ok = False
    else:
        print(f"  ✅ 名称匹配率: {results['match_rate']:.1f}%")

    if results["avg_distance_m"] > 2000:
        print(
            f"  ❌ 平均坐标偏差过大: {results['avg_distance_m']:.1f}米 (期望 ≤ 2000米)"
        )
        ok = False
    else:
        print(f"  ✅ 平均坐标偏差: {results['avg_distance_m']:.1f}米")

    if results["scraper_count"] == 0:
        print("  ❌ Scraper 未返回任何结果")
        ok = False
    else:
        print(f"  ✅ Scraper 返回结果数: {results['scraper_count']}")

    if not ok:
        print("\n⚠️ 部分断言未通过，请检查差异详情。")
        sys.exit(1)

    print("\n🎉 测试全部通过！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
