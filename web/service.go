package web

import (
	"context"
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type Service struct {
	repo       JobRepository
	dataFolder string
}

func NewService(repo JobRepository, dataFolder string) *Service {
	return &Service{
		repo:       repo,
		dataFolder: dataFolder,
	}
}

func (s *Service) Create(ctx context.Context, job *Job) error {
	return s.repo.Create(ctx, job)
}

func (s *Service) All(ctx context.Context, page int) ([]Job, error) {
	limit := 10
	offset := (page - 1) * limit
	if offset < 0 {
		offset = 0
	}
	jobs, err := s.repo.Select(ctx, SelectParams{Limit: limit, Offset: offset})
	if err != nil {
		return nil, err
	}
	// 设置每个 job 的页码，用于前端分页显示
	for i := range jobs {
		jobs[i].Page = page
	}
	return jobs, nil
}

func (s *Service) Get(ctx context.Context, id string) (Job, error) {
	return s.repo.Get(ctx, id)
}

func (s *Service) Delete(ctx context.Context, id string) error {
	if strings.Contains(id, "/") || strings.Contains(id, "\\") || strings.Contains(id, "..") {
		return fmt.Errorf("invalid file name")
	}

	datapath := filepath.Join(s.dataFolder, id+".csv")

	if _, err := os.Stat(datapath); err == nil {
		if err := os.Remove(datapath); err != nil {
			return err
		}
	} else if !os.IsNotExist(err) {
		return err
	}

	return s.repo.Delete(ctx, id)
}

func (s *Service) Update(ctx context.Context, job *Job) error {
	return s.repo.Update(ctx, job)
}

func (s *Service) SelectPending(ctx context.Context) ([]Job, error) {
	return s.repo.Select(ctx, SelectParams{Status: StatusPending, Limit: 1})
}

func (s *Service) GetCSV(_ context.Context, id string) (string, error) {
	if strings.Contains(id, "/") || strings.Contains(id, "\\") || strings.Contains(id, "..") {
		return "", fmt.Errorf("invalid file name")
	}

	datapath := filepath.Join(s.dataFolder, id+".csv")

	if _, err := os.Stat(datapath); os.IsNotExist(err) {
		return "", fmt.Errorf("csv file not found for job %s", id)
	}

	return datapath, nil
}

// POIData 表示一个兴趣点数据
type POIData struct {
	ID        string  `json:"id"`
	Name      string  `json:"name"`
	Address   string  `json:"address"`
	Latitude  float64 `json:"lat"`
	Longitude float64 `json:"lng"`
	Phone     string  `json:"phone"`
	Website   string  `json:"website"`
	Category  string  `json:"category"`
	Rating    float64 `json:"rating"`
}

// GetPOIData 读取任务的 CSV 结果并返回 POI 数据
func (s *Service) GetPOIData(_ context.Context, id string) ([]POIData, error) {
	if strings.Contains(id, "/") || strings.Contains(id, "\\") || strings.Contains(id, "..") {
		return nil, fmt.Errorf("invalid file name")
	}

	datapath := filepath.Join(s.dataFolder, id+".csv")

	file, err := os.Open(datapath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	reader := csv.NewReader(file)
	records, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}

	if len(records) < 2 {
		return []POIData{}, nil
	}

	// 查找字段索引
	headers := records[0]
	var nameIdx, addrIdx, latIdx, lngIdx, phoneIdx, webIdx, catIdx, ratingIdx = -1, -1, -1, -1, -1, -1, -1, -1
	for i, h := range headers {
		switch h {
		case "title", "name":
			nameIdx = i
		case "address":
			addrIdx = i
		case "latitude":
			latIdx = i
		case "longitude", "longtitude":
			lngIdx = i
		case "phone":
			phoneIdx = i
		case "website":
			webIdx = i
		case "category":
			catIdx = i
		case "review_rating":
			ratingIdx = i
		}
	}

	var pois []POIData
	for i, record := range records[1:] {
		poi := POIData{
			ID: fmt.Sprintf("%s-%d", id, i),
		}

		if nameIdx >= 0 && nameIdx < len(record) {
			poi.Name = record[nameIdx]
		}
		if addrIdx >= 0 && addrIdx < len(record) {
			poi.Address = record[addrIdx]
		}
		if phoneIdx >= 0 && phoneIdx < len(record) {
			poi.Phone = record[phoneIdx]
		}
		if webIdx >= 0 && webIdx < len(record) {
			poi.Website = record[webIdx]
		}
		if catIdx >= 0 && catIdx < len(record) {
			poi.Category = record[catIdx]
		}
		if latIdx >= 0 && latIdx < len(record) {
			poi.Latitude, _ = strconv.ParseFloat(record[latIdx], 64)
		}
		if lngIdx >= 0 && lngIdx < len(record) {
			poi.Longitude, _ = strconv.ParseFloat(record[lngIdx], 64)
		}
		if ratingIdx >= 0 && ratingIdx < len(record) {
			poi.Rating, _ = strconv.ParseFloat(record[ratingIdx], 64)
		}

		// 只添加有有效坐标的数据
		if poi.Latitude != 0 || poi.Longitude != 0 {
			pois = append(pois, poi)
		}
	}

	return pois, nil
}
