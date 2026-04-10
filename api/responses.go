package api

import (
	"fmt"
	"strconv"
	"strings"
	"time"
)

// GmapData represents Google Maps scrape results data.
type GmapData any

// ErrorResponse represents an error response
// @Description 请求失败时返回的错误响应
type ErrorResponse struct {
	Message string `json:"message" example:"invalid request body"`
}

// HealthCheckResponse represents a health check response
// @Description 指示服务状态的健康检查响应
type HealthCheckResponse struct {
	Status string `json:"status" example:"ok"`
}

// ScrapeRequest represents a request to scrape Google Maps
// @Description 提交抓取任务的请求体
type ScrapeRequest struct {
	// 搜索关键词（例如："纽约的餐厅"）
	Keyword string `json:"keyword" example:"restaurants in New York"`
	// 结果语言代码（默认："zh-CN"）
	Lang string `json:"lang,omitempty" example:"zh-CN"`
	// 分页的最大深度（默认：1，最大：100）
	MaxDepth int `json:"max_depth,omitempty" example:"1"`
	// 是否从网站中提取电子邮件地址
	Email bool `json:"email,omitempty" example:"false"`
	// 地理坐标，格式为 "纬度,经度"
	GeoCoordinates string `json:"geo_coordinates,omitempty" example:"40.7128,-74.0060"`
	// 地图搜索缩放级别 (1-21)
	Zoom int `json:"zoom,omitempty" example:"14"`
	// 搜索半径（公里）
	Radius float64 `json:"radius,omitempty" example:"5.0"`
	// 使用快速模式（使用隐身 HTTP 请求代替浏览器）
	FastMode bool `json:"fast_mode,omitempty" example:"false"`
	// 提取更多评论
	ExtraReviews bool `json:"extra_reviews,omitempty" example:"false"`
	// 任务超时时间，单位秒（1-300，默认：300）
	Timeout int `json:"timeout,omitempty" example:"300"`
}

func (r *ScrapeRequest) Validate() error {
	if r.Keyword == "" {
		return fmt.Errorf("keyword is required")
	}

	if r.GeoCoordinates != "" {
		if strings.Count(r.GeoCoordinates, ",") != 1 {
			return fmt.Errorf("geo_coordinates must contain exactly one comma")
		}

		latStr, lonStr, ok := strings.Cut(r.GeoCoordinates, ",")
		if !ok {
			return fmt.Errorf("geo_coordinates must be in format 'lat,lon'")
		}

		lat, err := strconv.ParseFloat(strings.TrimSpace(latStr), 64)
		if err != nil {
			return fmt.Errorf("invalid latitude: %w", err)
		}

		lon, err := strconv.ParseFloat(strings.TrimSpace(lonStr), 64)
		if err != nil {
			return fmt.Errorf("invalid longitude: %w", err)
		}

		if lat < -90 || lat > 90 {
			return fmt.Errorf("latitude must be between -90 and 90")
		}

		if lon < -180 || lon > 180 {
			return fmt.Errorf("longitude must be between -180 and 180")
		}
	}

	if r.FastMode {
		if r.GeoCoordinates == "" {
			return fmt.Errorf("geo_coordinates are required in fast mode")
		}

		if r.Zoom == 0 {
			return fmt.Errorf("zoom is required in fast mode")
		}
	}

	if r.Zoom != 0 && (r.Zoom < 1 || r.Zoom > 21) {
		return fmt.Errorf("zoom must be between 1 and 21")
	}

	if r.Radius < 0 {
		return fmt.Errorf("radius must be non-negative")
	}

	if r.MaxDepth < 0 || r.MaxDepth > 100 {
		return fmt.Errorf("max_depth must be between 0 and 100")
	}

	if r.Timeout < 1 || r.Timeout > 300 {
		return fmt.Errorf("timeout must be between 1 and 300 seconds")
	}

	return nil
}

func (r *ScrapeRequest) SetDefaults() {
	if r.Lang == "" {
		r.Lang = "en"
	}

	if r.MaxDepth == 0 {
		r.MaxDepth = 1
	}

	if r.Timeout == 0 {
		r.Timeout = 300 // 5 minutes default
	}
}

// ScrapeResponse represents the response after submitting a scrape job
// @Description 成功提交抓取任务后返回的响应
type ScrapeResponse struct {
	// 唯一任务标识符
	JobID string `json:"job_id" example:"kYzR8xLmNpQvWjX3"`
	// 当前任务状态
	Status string `json:"status" example:"pending"`
}

// ListJobsRequest represents parameters for listing jobs
// @Description 用于分页和过滤任务列表的查询参数
type ListJobsRequest struct {
	// 按任务状态过滤 (available, running, completed, cancelled, discarded, pending, retryable, scheduled)
	State string `json:"state,omitempty" example:"completed"`
	// 返回的任务数量（默认：20，最大：100）
	Limit int `json:"limit,omitempty" example:"20"`
	// 用于分页的游标（来自上一次请求的响应）
	Cursor string `json:"cursor,omitempty" example:""`
}

// JobSummary represents a job without result data
// @Description 不包含完整结果数据的任务摘要
type JobSummary struct {
	// 唯一任务标识符
	JobID string `json:"job_id" example:"kYzR8xLmNpQvWjX3"`
	// 当前任务状态
	Status string `json:"status" example:"completed"`
	// 用于此任务的搜索关键词
	Keyword string `json:"keyword" example:"restaurants in New York"`
	// 任务创建时间
	CreatedAt time.Time `json:"created_at" example:"2024-01-15T10:30:00Z"`
	// 任务开始处理的时间
	StartedAt *time.Time `json:"started_at,omitempty" example:"2024-01-15T10:30:05Z"`
	// 任务完成时间
	CompletedAt *time.Time `json:"completed_at,omitempty" example:"2024-01-15T10:35:00Z"`
	// 找到的结果数量
	ResultCount int `json:"result_count" example:"25"`
	// 任务失败时的错误信息
	Error string `json:"error,omitempty" example:""`
}

// ListJobsResponse represents a paginated list of jobs
// @Description 带有下一页游标的分页任务列表
type ListJobsResponse struct {
	// 任务列表
	Jobs []JobSummary `json:"jobs"`
	// 下一页的游标（如果没有更多结果则为空）
	NextCursor string `json:"next_cursor,omitempty" example:"eyJpZCI6MTIzfQ=="`
	// 是否有更多结果
	HasMore bool `json:"has_more" example:"true"`
}

// JobStatusResponse represents the status of a scrape job
// @Description 抓取任务的详细状态（完成后将包含结果）
type JobStatusResponse struct {
	// 唯一任务标识符
	JobID string `json:"job_id" example:"kYzR8xLmNpQvWjX3"`
	// 当前任务状态 (pending, running, completed, failed)
	Status string `json:"status" example:"completed"`
	// 用于此任务的搜索关键词
	Keyword string `json:"keyword" example:"restaurants in New York"`
	// 任务创建时间
	CreatedAt time.Time `json:"created_at" example:"2024-01-15T10:30:00Z"`
	// 任务开始处理的时间
	StartedAt *time.Time `json:"started_at,omitempty" example:"2024-01-15T10:30:05Z"`
	// 任务完成时间
	CompletedAt *time.Time `json:"completed_at,omitempty" example:"2024-01-15T10:35:00Z"`
	// 抓取结果（地点数据数组）
	Results GmapData `json:"results,omitempty"`
	// 任务失败时的错误信息
	Error string `json:"error,omitempty" example:""`
	// 找到的结果数量
	ResultCount int `json:"result_count" example:"25"`
}

// DeleteJobResponse represents the response after requesting job deletion
// @Description 成功将任务加入删除队列后返回的响应
type DeleteJobResponse struct {
	// 状态信息
	Message string `json:"message" example:"deletion queued"`
}
