# Changelog

## 3.1.0
- Linux support: placeholder `sleep` process with the game's executable name, `install_linux.sh`, desktop entry.
- Project restructured into a Python package with tests and GitHub Actions (CI + release builds).
- Fixed a method name that clashed with `threading.Thread._stop` and broke clean shutdown.

## 3.0.0
- New web-based interface (Arabic/English, RTL), cover-art grid, floating "now playing" dock.
- Steam library with Steam cover art, instant startup from cache, infinite-scroll grid.
- Placeholder-process detection (how Discord really detects games) plus Rich Presence fallback.
