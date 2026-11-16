//go:build windows

package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestWindowsChromeDiscovery(t *testing.T) {
	root := t.TempDir()
	for _, name := range []string{"ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"} {
		t.Setenv(name, filepath.Join(root, name))
	}
	t.Setenv("PATH", root)
	if _, err := findWindowsChrome(); err == nil || !strings.Contains(err.Error(), "Install Chrome") {
		t.Fatalf("expected Chrome installation guidance, got %v", err)
	}
	for _, name := range []string{"LOCALAPPDATA", "ProgramFiles(x86)", "ProgramFiles"} {
		path := filepath.Join(os.Getenv(name), "Google", "Chrome", "Application", "chrome.exe")
		if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, nil, 0600); err != nil {
			t.Fatal(err)
		}
		got, err := findWindowsChrome()
		if err != nil || got != path {
			t.Fatalf("expected %q, got %q (%v)", path, got, err)
		}
	}
}
