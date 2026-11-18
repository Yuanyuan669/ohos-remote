//go:build linux

package main

import (
	"fmt"
	"sync"
	"syscall"
	"time"
	"unsafe"
)

const (
	evSyn = 0
	evKey = 1
	evAbs = 3

	absX        = 0x00
	absY        = 0x01
	absPressure = 0x18
	btnTouch    = 0x14a

	synReport = 0

	uiDevCreate  = 0x5501
	uiDevDestroy = 0x5502
	uiSetEvBit   = 0x40045564
	uiSetKeyBit  = 0x40045565
	uiSetAbsBit  = 0x40045567
	uiSetPhys    = 0x4008556c
	uiSetPropBit = 0x4004556e
)

type inputID struct {
	Bus, Vendor, Product, Version uint16
}

type uinputUserDev struct {
	Name    [80]byte
	ID      inputID
	FF      uint32
	Absmax  [64]int32
	Absmin  [64]int32
	Absfuzz [64]int32
	Absflat [64]int32
}

type inputEvent struct {
	Sec, Usec int64
	Type      uint16
	Code      uint16
	Value     int32
}

type TouchDevice struct {
	fd   int
	mu   sync.Mutex
	maxX int32
	maxY int32
}

func ioctlPtr(fd int, req uintptr, arg unsafe.Pointer) error {
	_, _, errno := syscall.Syscall(syscall.SYS_IOCTL, uintptr(fd), req, uintptr(arg))
	if errno != 0 {
		return errno
	}
	return nil
}

func ioctlVal(fd int, req uintptr, val uintptr) error {
	_, _, errno := syscall.Syscall(syscall.SYS_IOCTL, uintptr(fd), req, val)
	if errno != 0 {
		return errno
	}
	return nil
}

func emit(fd int, typ, code uint16, value int32) error {
	now := time.Now()
	ev := inputEvent{Sec: now.Unix(), Usec: int64(now.Nanosecond() / 1000), Type: typ, Code: code, Value: value}
	b := unsafe.Slice((*byte)(unsafe.Pointer(&ev)), unsafe.Sizeof(ev))
	_, err := syscall.Write(fd, b)
	return err
}

func OpenTouchDevice(width, height int) (*TouchDevice, error) {
	fd, err := syscall.Open("/dev/uinput", syscall.O_WRONLY|syscall.O_NONBLOCK, 0)
	if err != nil {
		return nil, err
	}
	fail := func(err error) (*TouchDevice, error) {
		syscall.Close(fd)
		return nil, err
	}
	for _, ev := range []uintptr{evSyn, evKey, evAbs} {
		if err := ioctlVal(fd, uiSetEvBit, ev); err != nil {
			return fail(fmt.Errorf("evbit %d: %w", ev, err))
		}
	}
	if err := ioctlVal(fd, uiSetKeyBit, btnTouch); err != nil {
		return fail(err)
	}
	for _, code := range []uintptr{absX, absY, absPressure} {
		if err := ioctlVal(fd, uiSetAbsBit, code); err != nil {
			return fail(fmt.Errorf("absbit %d: %w", code, err))
		}
	}
	ioctlVal(fd, uiSetPropBit, 1)
	phys := []byte(fmt.Sprintf("touchscreen%d/%d\x00", syscall.Getpid(), syscall.Getpid()))
	if err := ioctlPtr(fd, uiSetPhys, unsafe.Pointer(&phys[0])); err != nil {
		return fail(fmt.Errorf("phys: %w", err))
	}
	dev := uinputUserDev{ID: inputID{Bus: 0x03, Vendor: 0x6006, Product: 0x6006, Version: 1}}
	copy(dev.Name[:], "Virtual SingleTouchScreen")
	dev.Absmax[absX] = int32(width)
	dev.Absmax[absY] = int32(height)
	dev.Absmax[absPressure] = 100
	b := unsafe.Slice((*byte)(unsafe.Pointer(&dev)), unsafe.Sizeof(dev))
	if _, err := syscall.Write(fd, b); err != nil {
		return fail(err)
	}
	if err := ioctlVal(fd, uiDevCreate, 0); err != nil {
		return fail(fmt.Errorf("create: %w", err))
	}
	time.Sleep(300 * time.Millisecond)
	return &TouchDevice{fd: fd, maxX: int32(width - 1), maxY: int32(height - 1)}, nil
}

func (t *TouchDevice) clamp(x, y int) (int32, int32) {
	if x < 0 {
		x = 0
	}
	if y < 0 {
		y = 0
	}
	if int32(x) > t.maxX {
		x = int(t.maxX)
	}
	if int32(y) > t.maxY {
		y = int(t.maxY)
	}
	return int32(x), int32(y)
}

func (t *TouchDevice) down(x, y int32) error {
	if err := emit(t.fd, evAbs, absX, x); err != nil {
		return err
	}
	if err := emit(t.fd, evAbs, absY, y); err != nil {
		return err
	}
	if err := emit(t.fd, evAbs, absPressure, 5); err != nil {
		return err
	}
	if err := emit(t.fd, evKey, btnTouch, 1); err != nil {
		return err
	}
	return emit(t.fd, evSyn, synReport, 0)
}

func (t *TouchDevice) up() error {
	if err := emit(t.fd, evAbs, absPressure, 0); err != nil {
		return err
	}
	if err := emit(t.fd, evKey, btnTouch, 0); err != nil {
		return err
	}
	return emit(t.fd, evSyn, synReport, 0)
}

func (t *TouchDevice) Tap(x, y int, hold time.Duration) error {
	t.mu.Lock()
	defer t.mu.Unlock()
	px, py := t.clamp(x, y)
	if err := t.down(px, py); err != nil {
		return err
	}
	time.Sleep(hold)
	return t.up()
}

func (t *TouchDevice) Swipe(x1, y1, x2, y2 int, duration time.Duration) error {
	t.mu.Lock()
	defer t.mu.Unlock()
	if duration < 20*time.Millisecond {
		duration = 20 * time.Millisecond
	}
	steps := int(duration / (8 * time.Millisecond))
	if steps < 2 {
		steps = 2
	}
	sx, sy := t.clamp(x1, y1)
	ex, ey := t.clamp(x2, y2)
	if err := t.down(sx, sy); err != nil {
		return err
	}
	stepDelay := duration / time.Duration(steps)
	for i := 1; i <= steps; i++ {
		x := sx + (ex-sx)*int32(i)/int32(steps)
		y := sy + (ey-sy)*int32(i)/int32(steps)
		if err := emit(t.fd, evAbs, absX, x); err != nil {
			return err
		}
		if err := emit(t.fd, evAbs, absY, y); err != nil {
			return err
		}
		if err := emit(t.fd, evSyn, synReport, 0); err != nil {
			return err
		}
		time.Sleep(stepDelay)
	}
	return t.up()
}

func (t *TouchDevice) Close() {
	if t == nil || t.fd < 0 {
		return
	}
	ioctlVal(t.fd, uiDevDestroy, 0)
	syscall.Close(t.fd)
	t.fd = -1
}
