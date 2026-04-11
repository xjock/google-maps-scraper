package installplaywright

import (
	"context"
	"fmt"

	"github.com/playwright-community/playwright-go"
	"github.com/xjock/google-maps-scraper/runner"
)

type installer struct {
}

func New(cfg *runner.Config) (runner.Runner, error) {
	if cfg.RunMode != runner.RunModeInstallPlaywright {
		return nil, fmt.Errorf("%w: %d", runner.ErrInvalidRunMode, cfg.RunMode)
	}

	return &installer{}, nil
}

func (i *installer) Run(context.Context) error {
	opts := []*playwright.RunOptions{
		{
			Browsers: []string{"chromium"},
		},
	}

	return playwright.Install(opts...)
}

func (i *installer) Close(context.Context) error {
	return nil
}
