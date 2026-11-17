package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math/rand"
	"net"
	"net/http"
	"os"
	"os/exec"
	"sync"
	"time"

	"github.com/gorilla/websocket"

	_ "embed"
)

//go:embed index.html
var pageHTML []byte

type command struct {
	Type string `json:"t"`
	X    int    `json:"x"`
	Y    int    `json:"y"`
	X2   int    `json:"x2"`
	Y2   int    `json:"y2"`
	Text string `json:"text"`
	Code int    `json:"code"`
}

var (
	token     string
	interval  time.Duration
	framePath = "/data/local/tmp/ohos_agent.jpeg"
	upgrader  = websocket.Upgrader{
		ReadBufferSize:  4096,
		WriteBufferSize: 1 << 20,
		CheckOrigin:     func(r *http.Request) bool { return true },
	}
	clientsMu sync.Mutex
	clients   = map[*websocket.Conn]struct{}{}
)

func run(cmd string, args ...string) {
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	c := exec.CommandContext(ctx, cmd, args...)
	if out, err := c.CombinedOutput(); err != nil {
		log.Printf("%s %v: %v %s", cmd, args, err, string(out))
	}
}

func captureOnce() []byte {
	os.Remove(framePath)
	start := time.Now()
	run("/bin/snapshot_display", "-f", framePath)
	data, err := os.ReadFile(framePath)
	if err != nil || len(data) == 0 {
		log.Printf("snapshot empty after %v err=%v", time.Since(start), err)
		return nil
	}
	return data
}

func hasClients() bool {
	clientsMu.Lock()
	defer clientsMu.Unlock()
	return len(clients) > 0
}

func broadcast(data []byte) {
	clientsMu.Lock()
	defer clientsMu.Unlock()
	for c := range clients {
		if err := c.WriteMessage(websocket.BinaryMessage, data); err != nil {
			c.Close()
			delete(clients, c)
		}
	}
}

func captureLoop() {
	lastLog := time.Now()
	for {
		n := 0
		clientsMu.Lock()
		n = len(clients)
		clientsMu.Unlock()
		if n > 0 {
			frame := captureOnce()
			if frame != nil {
				broadcast(frame)
				if time.Since(lastLog) > 5*time.Second {
					log.Printf("capture ok %d bytes clients=%d", len(frame), n)
					lastLog = time.Now()
				}
			}
		}
		time.Sleep(interval)
	}
}

func handleWS(w http.ResponseWriter, r *http.Request) {
	if r.URL.Query().Get("token") != token {
		http.Error(w, "bad token", http.StatusUnauthorized)
		return
	}
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	clientsMu.Lock()
	clients[conn] = struct{}{}
	clientsMu.Unlock()
	defer func() {
		clientsMu.Lock()
		delete(clients, conn)
		clientsMu.Unlock()
		conn.Close()
	}()

	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			return
		}
		var cmd command
		if json.Unmarshal(data, &cmd) != nil {
			continue
		}
		switch cmd.Type {
		case "tap":
			uiTap(cmd.X, cmd.Y)
		case "swipe":
			uiSwipe(cmd.X, cmd.Y, cmd.X2, cmd.Y2)
		case "text":
			uiText(cmd.Text)
		case "key":
			uiKey(cmd.Code)
		}
	}
}

func itoa(v int) string {
	return fmt.Sprintf("%d", v)
}

func uiTap(x, y int) {
	run("/bin/uinput", "-T", "-c", itoa(x), itoa(y))
}

func uiSwipe(x1, y1, x2, y2 int) {
	run("/bin/uinput", "-T", "-m", itoa(x1), itoa(y1), itoa(x2), itoa(y2), "300")
}

func uiKey(code int) {
	run("/bin/uinput", "-K", "-d", itoa(code), "-u", itoa(code))
}

func keyCode(r rune) (int, bool) {
	switch {
	case r >= 'a' && r <= 'z':
		return 30 + int(r-'a'), true
	case r >= 'A' && r <= 'Z':
		return 30 + int(r-'A'), true
	case r >= '1' && r <= '9':
		return 2 + int(r-'1'), true
	case r == '0':
		return 11, true
	}
	switch r {
	case ' ':
		return 57, true
	case '\n':
		return 28, true
	case '.':
		return 52, true
	case ',':
		return 51, true
	case '-':
		return 12, true
	case '/':
		return 53, true
	case ';':
		return 39, true
	case '=':
		return 13, true
	case '[':
		return 26, true
	case ']':
		return 27, true
	case '\'':
		return 40, true
	case '\\':
		return 43, true
	}
	return 0, false
}

func uiText(text string) {
	for _, r := range text {
		code, ok := keyCode(r)
		if !ok {
			continue
		}
		shift := r >= 'A' && r <= 'Z'
		if shift {
			run("/bin/uinput", "-K", "-d", "42")
		}
		run("/bin/uinput", "-K", "-d", itoa(code), "-u", itoa(code))
		if shift {
			run("/bin/uinput", "-K", "-u", "42")
		}
		time.Sleep(30 * time.Millisecond)
	}
}

func localIP() string {
	addrs, err := net.InterfaceAddrs()
	if err != nil {
		return "127.0.0.1"
	}
	for _, a := range addrs {
		if ipnet, ok := a.(*net.IPNet); ok && !ipnet.IP.IsLoopback() && ipnet.IP.To4() != nil {
			return ipnet.IP.String()
		}
	}
	return "127.0.0.1"
}

func main() {
	addr := flag.String("addr", ":8765", "listen address")
	tok := flag.String("token", "", "access token (default random)")
	ms := flag.Int("interval", 250, "capture interval ms")
	flag.Parse()
	interval = time.Duration(*ms) * time.Millisecond
	token = *tok
	if token == "" {
		token = fmt.Sprintf("%06d", rand.Intn(1000000))
	}

	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write(pageHTML)
	})
	http.HandleFunc("/ws", handleWS)

	go captureLoop()
	fmt.Printf("ohos-agent listening %s\n", *addr)
	fmt.Printf("open: http://%s%s/?token=%s\n", localIP(), *addr, token)
	log.Fatal(http.ListenAndServe(*addr, nil))
}
