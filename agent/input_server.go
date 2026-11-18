package main

import (
	"bufio"
	"fmt"
	"log"
	"net"
	"strconv"
	"strings"
	"time"
)

func startInputServer(addr string, touch *TouchDevice) error {
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		return err
	}
	log.Printf("input server listening %s", addr)
	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				log.Printf("input accept: %v", err)
				return
			}
			go handleInputConn(conn, touch)
		}
	}()
	return nil
}

func handleInputConn(conn net.Conn, touch *TouchDevice) {
	defer conn.Close()
	if tcp, ok := conn.(*net.TCPConn); ok {
		tcp.SetNoDelay(true)
	}
	sc := bufio.NewScanner(conn)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		if err := dispatchInput(touch, line); err != nil {
			log.Printf("input %q: %v", line, err)
		}
	}
}

func dispatchInput(touch *TouchDevice, line string) error {
	fields := strings.Fields(line)
	if len(fields) == 0 {
		return fmt.Errorf("empty")
	}
	atoi := func(s string) (int, error) {
		v, err := strconv.Atoi(s)
		if err != nil {
			return 0, fmt.Errorf("bad number %q", s)
		}
		return v, nil
	}
	switch fields[0] {
	case "ping":
		return nil
	case "tap":
		if len(fields) < 3 {
			return fmt.Errorf("tap x y")
		}
		x, err := atoi(fields[1])
		if err != nil {
			return err
		}
		y, err := atoi(fields[2])
		if err != nil {
			return err
		}
		if touch == nil {
			return fmt.Errorf("no touch device")
		}
		return touch.Tap(x, y, 20*time.Millisecond)
	case "swipe":
		if len(fields) < 5 {
			return fmt.Errorf("swipe x1 y1 x2 y2 [ms]")
		}
		vals := make([]int, 4)
		for i := 0; i < 4; i++ {
			v, err := atoi(fields[i+1])
			if err != nil {
				return err
			}
			vals[i] = v
		}
		dur := 150 * time.Millisecond
		if len(fields) >= 6 {
			ms, err := atoi(fields[5])
			if err != nil {
				return err
			}
			dur = time.Duration(ms) * time.Millisecond
		}
		if touch == nil {
			return fmt.Errorf("no touch device")
		}
		return touch.Swipe(vals[0], vals[1], vals[2], vals[3], dur)
	default:
		return fmt.Errorf("unknown command %q", fields[0])
	}
}
