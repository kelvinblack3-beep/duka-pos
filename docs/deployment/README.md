# Deployment

Status: **PLANNED**. No shop deployment has been tested.

## Default path

Native Python 3.12+ on the shop PC. Virtual environment. SQLite file on
local disk. Browser kiosk for the cashier.

Docker is **optional** and is **not** required. There is no Dockerfile and
no Compose file in Milestone 0. Do not add them unless a later ADR says so.

## What must be portable later

- application code
- SQLite database
- configuration (secrets stay out of git)
- later customizations, assets, reports, backups

## Not in M0

Installers, Windows service wrappers, auto-start, backup schedules, VPN,
and cloud hosting. Documented here so they are not mistaken for existing
features.
