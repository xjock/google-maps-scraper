package gmaps

import (
	"context"
	"net/http"

	"github.com/google/uuid"
	"github.com/gosom/scrapemate"
)

// WriteEntryJob 是一个简单的 Job，用于将 Entry 写入结果
// 这是为了解决 SearchJob 返回多个 entries 时的写入问题
type WriteEntryJob struct {
	scrapemate.Job
	Entry *Entry
}

// NewWriteEntryJob 创建一个新的 WriteEntryJob
func NewWriteEntryJob(entry *Entry) *WriteEntryJob {
	return &WriteEntryJob{
		Job: scrapemate.Job{
			ID:     uuid.New().String(),
			Method: http.MethodGet,
			URL:    "internal://write-entry",
		},
		Entry: entry,
	}
}

// Process 直接返回 Entry 作为结果
func (j *WriteEntryJob) Process(_ context.Context, _ *scrapemate.Response) (any, []scrapemate.IJob, error) {
	// 直接返回 Entry，让 ResultWriter 写入
	return j.Entry, nil, nil
}

// ProcessOnFetchError 总是返回 false，因为这是内部任务
func (j *WriteEntryJob) ProcessOnFetchError() bool {
	return false
}

// GetURL 返回内部 URL
func (j *WriteEntryJob) GetURL() string {
	return j.URL
}
