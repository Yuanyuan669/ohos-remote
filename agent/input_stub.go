//go:build !linux

package main

import (
	"fmt"
	"time"
)

type TouchDevice struct{}

func OpenTouchDevice(width, height int) (*TouchDevice, error) {
	return nil, fmt.Errorf("touch input unsupported on this OS")
}

func (t *TouchDevice) Tap(x, y int, hold time.Duration) error {
	return fmt.Errorf("touch input unsupported on this OS")
}

func (t *TouchDevice) Swipe(x1, y1, x2, y2 int, duration time.Duration) error {
	return fmt.Errorf("touch input unsupported on this OS")
}

func (t *TouchDevice) Close() {}
