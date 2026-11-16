//go:build windows

package main

import (
	"errors"
	"os"
	"os/exec"
	"path/filepath"
)

func launchBrowser(appURL, dataDir string) error {
	chrome, err := findWindowsChrome()
	if err != nil {
		return err
	}
	cmd := exec.Command(chrome, "--app="+appURL, "--user-data-dir="+filepath.Join(dataDir, "profile"), "--window-size=1440,920", "--no-first-run", "--no-default-browser-check")
	if err := cmd.Start(); err != nil {
		return err
	}
	go func() { _ = cmd.Wait() }()
	return nil
}

func findWindowsChrome() (string, error) {
	for _, base := range []string{os.Getenv("ProgramFiles"), os.Getenv("ProgramFiles(x86)"), os.Getenv("LOCALAPPDATA")} {
		if base == "" {
			continue
		}
		chrome := filepath.Join(base, "Google", "Chrome", "Application", "chrome.exe")
		if fileExists(chrome) {
			return chrome, nil
		}
	}
	if chrome, err := exec.LookPath("chrome.exe"); err == nil {
		return chrome, nil
	}
	return "", errors.New("Google Chrome was not found. Install Chrome, then reopen NTK SoundLab Studio")
}
