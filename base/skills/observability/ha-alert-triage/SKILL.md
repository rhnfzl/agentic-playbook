---
name: ha-alert-triage
description: "Use when the user pastes a Telegram or Pushover notification from the homelab (energy/health/boiler/commute/automation-health/solar/weather/morning-briefing/weekly-energy/sleep-debt/train-update) and asks what triggered it, whether the wording is right, whether the threshold makes sense, or why one channel rendered differently from the other. Triggers on got this telegram, got this on pushover, what is this alert, why did I get, this looks wrong, is this real, false alarm, why is it different on telegram vs pushover, morning briefing is wrong, sleep debt alert, train update, HA notification, automation health alert."
version: 1.0.0
owner: rehan-8v
last_reviewed: 2026-05-24
---

# Homelab Alert Triage

A bounded loop for diagnosing a pasted homelab notification. The aim is to
finish with one of: real-trigger + thresholds-correct, real-trigger +
thresholds-need-tuning, rendering-bug, dual-channel-divergence, or
false-positive-from-data-gap. Do not propose a fix until classification is
done.

## When to invoke

The user pastes or screenshots one of:

- A Telegram or Pushover message starting with an emoji header (`📡`, `📊`,
  `🌡️`, `🚂`, `🚨`, `🩺`, `☀️`) and asks for diagnosis.
- An Automation Health Alert ("failed to set up", "failed to render").
- A Morning Briefing / Weekly Energy / Sleep Debt / Train Update body that
  looks malformed (broken wrap, missing rows, wrong number).

Do NOT invoke this skill for:
- New alert design ("add an alert for X"): that is regular development.
- Notification routing config changes: that is in `docs/NOTIFICATIONS.md`.
- team work: wrong domain.
- Generic homelab debugging without a pasted alert body: use the
  `diagnose` skill instead. This skill is specifically scoped to
  diagnosing a *received* notification.

## Loop

1. **Identify the source automation.**
   - Search `config/homeassistant/automations/*.yaml` and
     `config/homeassistant/packages/notify.yaml` for the literal header
     string or a distinctive phrase from the body.
   - Record the automation id + slug + trigger.

2. **Reconstruct the trigger conditions.**
   - Read the `trigger:` and `condition:` blocks. Note any `for:` durations,
     numeric thresholds, time windows, and helper-state gates.
   - Cross-check thresholds against `docs/HEALTH_ALERTS.md` (for health),
     `docs/HA_AUTOMATIONS.md` (for commute / briefing / WFH),
     `docs/VAILLANT_BOILER.md` (for boiler), `docs/HA_LIGHTING.md` (for
     lighting). If a threshold is undocumented, flag that.

3. **Verify against live state.**
   - For sensor-driven alerts, query current + recent values via the HA
     MCP (`ha_get_state`, `ha_get_history`) or via the HA REST API. Do not
     guess at history.
   - For time-based alerts, confirm the trigger time matches the timestamp
     on the pasted message (Europe/Amsterdam).

4. **Check rendering against the validated pattern.**
   - Open `~/.claude/projects/<homelab-project-slug>/memory/reference_telegram_ha_notifications.md`
     and confirm: HTML parse_mode, no `<code>` tables, `{%- -%}` whitespace
     stripping, `namespace()` inside `{% for %}`, hero verdict in `<i>`,
     section headers `EMOJI <b>...</b>`.
   - For Telegram-vs-Pushover divergence, remember that Pushover routes via
     Apprise (strips inline keyboards, has different HTML handling). The
     `<code>` table failure mode causes Telegram bot-API timeouts under
     network jitter while Apprise renders fine.

5. **Validate the template render programmatically before proposing a fix.**
   - HA REST `POST /api/template` with the template body returns the exact
     output. This is safe and read-only. Do this BEFORE editing the YAML.
   - Do NOT call `POST /api/services/automation/trigger` from within this
     skill. Firing the automation re-publishes the alert to the user's
     phone and runs any follow-up actions (snapshot updates, helper
     writes). If end-to-end verification is needed, propose it as a
     separate step and wait for the user to invoke it themselves.

6. **Classify.** Report one of:

   | Class | Meaning | Next step |
   |---|---|---|
   | `real-trigger, thresholds-correct` | Alert fired correctly | None, or annotate "as designed" |
   | `real-trigger, thresholds-need-tuning` | Fired correctly, value not actionable | Propose new threshold + cite source doc |
   | `rendering-bug` | Trigger fine, output malformed | Apply Telegram-format pattern, retest via /api/template |
   | `dual-channel-divergence` | Telegram + Pushover differ unexpectedly | Check `<code>` tables, Apprise URL, `continue_on_error` masking |
   | `false-positive-from-data-gap` | Sensor unavailable / stale, fired anyway | Add availability gate or `not_unknown` condition; see `feedback_ha_resilience` |

## Guardrails

- This skill is diagnosis-first. Do not edit any automation YAML, package
  file, or template until the user has read the classification and
  explicitly asked for a fix. A pasted alert is a question, not an
  edit authorization.
- Do not call `automation.trigger` or any `script.*` service: those
  re-publish notifications to the user's devices and run helper
  side-effects.
- Do not run side-effect scripts ad-hoc (`solar_forecast.py`,
  `boiler_baseline.py`, `health_verify.py` all send real Telegram). Read
  source instead. See memory `feedback_side_effect_scripts`.
- Wrong-class fixes ship asymmetry between morning/evening or between
  zones. Classify before you propose a fix.
- When the user does ask for a fix and the target is one of the
  `automations/<domain>.yaml` files, edit it directly: the HA UI will
  create a duplicate in `automations.yaml` instead of rewriting the
  tracked file. After any edit, `./sync-from-homelab.sh` then commit.
- Continue-on-error on `script.notify_alert` can mask the failing leg.
  Always read `logs` after a failed alert, not just the message body.

## Common false starts

- Treating the pasted body as the whole story. The trigger reason often
  lives in a helper, not the visible payload. Always read the
  automation, not just the message.
- Assuming the wording is wrong when the data is wrong. Re-check the
  underlying entity before refactoring Jinja.
- Forgetting that `for: N min` triggers do NOT survive `ha core restart`.
  If the alert is "stuck-on" or never fires after an upgrade, see memory
  `reference_ha_for_triggers_dont_survive_restart`.

## Verification before reporting

Before closing the loop, confirm:

- The proposed cause matches the timestamp on the pasted message.
- The template render via `/api/template` produces the expected output.
- If a threshold tuning is proposed, it is grounded in `docs/HEALTH_ALERTS.md`
  or equivalent, not a vibe.
