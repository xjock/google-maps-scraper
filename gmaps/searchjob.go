package gmaps

import (
	"bytes"
	"context"
	"fmt"
	"net/http"

	"github.com/google/uuid"
	"github.com/gosom/scrapemate"
	"github.com/xjock/google-maps-scraper/exiter"
	"github.com/xjock/google-maps-scraper/grid" // <-- 新增：导入我们修改过的 grid 包
)

type SearchJobOptions func(*SearchJob)

type MapLocation struct {
	Lat     float64
	Lon     float64
	ZoomLvl float64
	Radius  float64
}

type MapSearchParams struct {
	Location  MapLocation
	Query     string
	ViewportW int
	ViewportH int
	Hl        string
	GeoJSON   string // <-- 新增：用于接收前端传来的 GeoJSON 边界数据
}

type SearchJob struct {
	scrapemate.Job

	params                  *MapSearchParams
	ExitMonitor             exiter.Exiter
	WriterManagedCompletion bool
}

func NewSearchJob(params *MapSearchParams, opts ...SearchJobOptions) *SearchJob {
	const (
		defaultPrio       = scrapemate.PriorityMedium
		defaultMaxRetries = 3
		baseURL           = "https://maps.google.com/search"
	)

	job := SearchJob{
		Job: scrapemate.Job{
			ID:         uuid.New().String(),
			Method:     http.MethodGet,
			URL:        baseURL,
			URLParams:  buildGoogleMapsParams(params),
			MaxRetries: defaultMaxRetries,
			Priority:   defaultPrio,
		},
	}

	job.params = params

	for _, opt := range opts {
		opt(&job)
	}

	return &job
}

func WithSearchJobExitMonitor(exitMonitor exiter.Exiter) SearchJobOptions {
	return func(j *SearchJob) {
		j.ExitMonitor = exitMonitor
	}
}

func WithSearchJobWriterManagedCompletion() SearchJobOptions {
	return func(j *SearchJob) {
		j.WriterManagedCompletion = true
	}
}

func (j *SearchJob) ProcessOnFetchError() bool {
	return true
}

func (j *SearchJob) Process(_ context.Context, resp *scrapemate.Response) (any, []scrapemate.IJob, error) {
	defer func() {
		resp.Document = nil
		resp.Body = nil
		resp.Meta = nil
	}()

	if resp.Error != nil {
		if j.ExitMonitor != nil {
			j.ExitMonitor.IncrSeedCompleted(1)
		}

		return nil, nil, resp.Error
	}

	body := removeFirstLine(resp.Body)
	if len(body) == 0 {
		if j.ExitMonitor != nil {
			j.ExitMonitor.IncrSeedCompleted(1)
		}

		return nil, nil, fmt.Errorf("empty response body")
	}

	entries, err := ParseSearchResults(body)
	if err != nil {
		if j.ExitMonitor != nil {
			j.ExitMonitor.IncrSeedCompleted(1)
		}

		return nil, nil, fmt.Errorf("failed to parse search results: %w", err)
	}

	// ==========================================
	// 核心逻辑修改：空间边界过滤 (Spatial Filtering)
	// ==========================================
	if j.params.GeoJSON != "" {
		// 1. 尝试解析 GeoJSON 多边形
		polygon, err := grid.ParseGeoJSONPolygon(j.params.GeoJSON)

		if err == nil && len(polygon) > 0 {
			// 2. 如果是多边形或矩形，使用精准的射线法过滤
			filtered := entries[:0] // Go 语言的高效原地(in-place)过滤切片技巧
			for _, entry := range entries {
				// 提取 POI 的经纬度 (假设 entry 中字段名为 Longitude 和 Latitude)
				pt := grid.Point{Lng: entry.Longtitude, Lat: entry.Latitude}

				// 仅保留在多边形内部的商家
				if grid.IsPointInPolygon(pt, polygon) {
					filtered = append(filtered, entry)
				}
			}
			entries = filtered
		} else {
			// 3. 如果解析为空（说明用户画的是圆形，或者是旧版任务），回退到默认的圆形半径过滤算法
			entries = filterAndSortEntriesWithinRadius(entries,
				j.params.Location.Lat,
				j.params.Location.Lon,
				j.params.Location.Radius,
			)
		}
	} else {
		// 如果完全没有传 GeoJSON，也走默认半径过滤
		entries = filterAndSortEntriesWithinRadius(entries,
			j.params.Location.Lat,
			j.params.Location.Lon,
			j.params.Location.Radius,
		)
	}
	// ==========================================

	if j.ExitMonitor != nil {
		j.ExitMonitor.IncrPlacesFound(len(entries))
		j.ExitMonitor.IncrSeedCompleted(1)

		if !j.WriterManagedCompletion {
			j.ExitMonitor.IncrPlacesCompleted(len(entries))
		}
	}

	return entries, nil, nil
}

func removeFirstLine(data []byte) []byte {
	if len(data) == 0 {
		return data
	}

	index := bytes.IndexByte(data, '\n')
	if index == -1 {
		return []byte{}
	}

	return data[index+1:]
}

func buildGoogleMapsParams(params *MapSearchParams) map[string]string {
	params.ViewportH = 800
	params.ViewportW = 600

	ans := map[string]string{
		"tbm":      "map",
		"authuser": "0",
		"hl":       params.Hl,
		"q":        params.Query,
	}

	pb := fmt.Sprintf("!4m12!1m3!1d3826.902183192154!2d%.4f!3d%.4f!2m3!1f0!2f0!3f0!3m2!1i%d!2i%d!4f%.1f!7i20!8i0"+
		"!10b1!12m22!1m3!18b1!30b1!34e1!2m3!5m1!6e2!20e3!4b0!10b1!12b1!13b1!16b1!17m1!3e1!20m3!5e2!6b1!14b1!46m1!1b0"+
		"!96b1!19m4!2m3!1i360!2i120!4i8",
		params.Location.Lon,
		params.Location.Lat,
		params.ViewportW,
		params.ViewportH,
		params.Location.ZoomLvl,
	)

	ans["pb"] = pb

	return ans
}
