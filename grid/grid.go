// Package grid provides utilities to divide a geographic bounding box into a
// grid of smaller cells. This is useful for overcoming Google Maps' ~120
// results-per-search limit: by splitting a large area into many small cells
// and issuing one search per cell, you can retrieve far more results.
package grid

import (
	"encoding/json"
	"fmt"
	"math"
	"strconv"
	"strings"
)

const kmPerDegreeLat = 111.32
const minCosLatitude = 1e-6

// BoundingBox represents a geographic rectangle defined by two corners.
type BoundingBox struct {
	MinLat float64
	MinLon float64
	MaxLat float64
	MaxLon float64
}

// ParseBoundingBox parses a string with format "minLat,minLon,maxLat,maxLon".
func ParseBoundingBox(s string) (BoundingBox, error) {
	parts := strings.Split(s, ",")
	if len(parts) != 4 {
		return BoundingBox{}, fmt.Errorf("invalid bounding box %q: expected format minLat,minLon,maxLat,maxLon", s)
	}

	vals := make([]float64, 4)

	for i, p := range parts {
		v, err := strconv.ParseFloat(strings.TrimSpace(p), 64)
		if err != nil {
			return BoundingBox{}, fmt.Errorf("invalid bounding box value %q: %w", p, err)
		}

		if math.IsNaN(v) || math.IsInf(v, 0) {
			return BoundingBox{}, fmt.Errorf("invalid bounding box value %q: must be finite", p)
		}

		vals[i] = v
	}

	bbox := BoundingBox{
		MinLat: vals[0],
		MinLon: vals[1],
		MaxLat: vals[2],
		MaxLon: vals[3],
	}

	if bbox.MinLat >= bbox.MaxLat {
		return BoundingBox{}, fmt.Errorf("minLat (%f) must be less than maxLat (%f)", bbox.MinLat, bbox.MaxLat)
	}

	if bbox.MinLon >= bbox.MaxLon {
		return BoundingBox{}, fmt.Errorf("minLon (%f) must be less than maxLon (%f)", bbox.MinLon, bbox.MaxLon)
	}

	if bbox.MinLat < -90 || bbox.MinLat > 90 {
		return BoundingBox{}, fmt.Errorf("minLat (%f) must be between -90 and 90", bbox.MinLat)
	}

	if bbox.MaxLat < -90 || bbox.MaxLat > 90 {
		return BoundingBox{}, fmt.Errorf("maxLat (%f) must be between -90 and 90", bbox.MaxLat)
	}

	if bbox.MinLon < -180 || bbox.MinLon > 180 {
		return BoundingBox{}, fmt.Errorf("minLon (%f) must be between -180 and 180", bbox.MinLon)
	}

	if bbox.MaxLon < -180 || bbox.MaxLon > 180 {
		return BoundingBox{}, fmt.Errorf("maxLon (%f) must be between -180 and 180", bbox.MaxLon)
	}

	return bbox, nil
}

// Cell represents the center point of a grid cell.
type Cell struct {
	Lat float64
	Lon float64
}

// GeoCoordinates returns the cell center in "lat,lon" format.
func (c Cell) GeoCoordinates() string {
	return fmt.Sprintf("%f,%f", c.Lat, c.Lon)
}

// Point represents a geographic coordinate used for polygon calculations.
type Point struct {
	Lng float64 // X 轴 (116.xxx)
	Lat float64 // Y 轴 (39.xxx)
}

// IsPointInPolygon uses the ray-casting algorithm to determine if a point is inside a polygon.
func IsPointInPolygon(point Point, polygon []Point) bool {
	if len(polygon) < 3 {
		return false
	}
	intersectCount := 0
	for i := 0; i < len(polygon); i++ {
		p1 := polygon[i]
		p2 := polygon[(i+1)%len(polygon)] // next vertex, wrapping around

		if ((p1.Lat > point.Lat) != (p2.Lat > point.Lat)) &&
			(point.Lng < (p2.Lng-p1.Lng)*(point.Lat-p1.Lat)/(p2.Lat-p1.Lat)+p1.Lng) {
			intersectCount++
		}
	}
	return intersectCount%2 == 1
}

// ParseGeoJSONPolygon 健壮的 GeoJSON 提取器
func ParseGeoJSONPolygon(geoJsonStr string) ([]Point, error) {
	if geoJsonStr == "" {
		return nil, nil
	}

	var root map[string]interface{}
	if err := json.Unmarshal([]byte(geoJsonStr), &root); err != nil {
		return nil, fmt.Errorf("failed to parse JSON: %w", err)
	}

	var geom map[string]interface{}
	typ, _ := root["type"].(string)

	// 支持解析各种层级的 GeoJSON 格式
	if typ == "FeatureCollection" {
		features, ok := root["features"].([]interface{})
		if ok && len(features) > 0 {
			f, _ := features[0].(map[string]interface{})
			geom, _ = f["geometry"].(map[string]interface{})
		}
	} else if typ == "Feature" {
		geom, _ = root["geometry"].(map[string]interface{})
	} else if typ == "Polygon" || typ == "Point" {
		geom = root
	}

	if geom == nil {
		return nil, fmt.Errorf("no geometry found in GeoJSON")
	}

	if geom["type"] != "Polygon" {
		if geom["type"] == "Point" {
			// 是原生圆形点，交由常规半径处理
			return nil, nil
		}
		return nil, fmt.Errorf("geometry is not a Polygon, got: %v", geom["type"])
	}

	coords, ok := geom["coordinates"].([]interface{})
	if !ok || len(coords) == 0 {
		return nil, fmt.Errorf("invalid coordinates array")
	}

	rings, ok := coords[0].([]interface{})
	if !ok {
		return nil, fmt.Errorf("invalid exterior ring")
	}

	var points []Point
	for _, pt := range rings {
		c, ok := pt.([]interface{})
		if ok && len(c) >= 2 {
			var lng, lat float64
			switch v := c[0].(type) {
			case float64:
				lng = v
			case int:
				lng = float64(v)
			}
			switch v := c[1].(type) {
			case float64:
				lat = v
			case int:
				lat = float64(v)
			}
			points = append(points, Point{Lng: lng, Lat: lat})
		}
	}
	return points, nil
}

func FilterCells(cells []Cell, polygon []Point) []Cell {
	if len(polygon) == 0 {
		return cells
	}
	var filtered []Cell
	for _, c := range cells {
		if IsPointInPolygon(Point{Lng: c.Lon, Lat: c.Lat}, polygon) {
			filtered = append(filtered, c)
		}
	}
	return filtered
}

// GenerateCells divides bbox into a grid where each cell is approximately
// cellSizeKm × cellSizeKm. It returns the center point of every cell.
func GenerateCells(bbox BoundingBox, cellSizeKm float64) []Cell {
	cellSizeKm = normalizeCellSizeKm(cellSizeKm)

	latStep := cellSizeKm / kmPerDegreeLat
	lonStep := calculateLonStep(bbox, cellSizeKm)

	var cells []Cell

	for lat := bbox.MinLat + latStep/2; lat < bbox.MaxLat; lat += latStep {
		for lon := bbox.MinLon + lonStep/2; lon < bbox.MaxLon; lon += lonStep {
			cells = append(cells, Cell{Lat: lat, Lon: lon})
		}
	}

	return cells
}

func EstimateCellCount(bbox BoundingBox, cellSizeKm float64) int {
	cellSizeKm = normalizeCellSizeKm(cellSizeKm)

	latStep := cellSizeKm / kmPerDegreeLat
	lonStep := calculateLonStep(bbox, cellSizeKm)

	latCells := int(math.Ceil((bbox.MaxLat - bbox.MinLat) / latStep))
	lonCells := int(math.Ceil((bbox.MaxLon - bbox.MinLon) / lonStep))

	if latCells < 0 {
		latCells = 0
	}

	if lonCells < 0 {
		lonCells = 0
	}

	return latCells * lonCells
}

func normalizeCellSizeKm(cellSizeKm float64) float64 {
	if cellSizeKm <= 0 {
		return 1.0
	}
	return cellSizeKm
}

func calculateLonStep(bbox BoundingBox, cellSizeKm float64) float64 {
	midLat := (bbox.MinLat + bbox.MaxLat) / 2
	cosMidLat := math.Cos(midLat * math.Pi / 180)

	if math.Abs(cosMidLat) < minCosLatitude {
		if cosMidLat < 0 {
			cosMidLat = -minCosLatitude
		} else {
			cosMidLat = minCosLatitude
		}
	}
	return cellSizeKm / (kmPerDegreeLat * cosMidLat)
}
