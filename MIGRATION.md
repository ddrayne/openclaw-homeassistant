# Upgrading from Clawd v1.2.x to OpenClaw v1.3.0

Clawd has been renamed to **OpenClaw** (via MoltBot). This integration now uses the `openclaw` domain. This is a breaking change that requires a clean reinstall — there is no automatic migration path.

## Step-by-step upgrade

1. **Remove the old integration**
   - Go to **Settings > Devices & Services**
   - Find "Clawd" and click the three dots > **Delete**
   - Note down your host, port, and token before deleting

2. **Remove old files from HACS**
   - Open **HACS > Integrations**
   - Find "Clawd Voice Assistant" and **remove** it (uninstall + remove from custom repositories)

3. **Delete the old `clawd` directory** (important!)
   - Using SSH, the File Editor add-on, or Samba, **manually delete** the `custom_components/clawd/` directory
   - HACS does **not** remove this automatically because the repository name changed
   - If you skip this step, Home Assistant will load both the old `clawd` and new `openclaw` integrations, causing errors in the log

4. **Restart Home Assistant**

5. **Install OpenClaw**
   - Open **HACS > Integrations > three dots > Custom repositories**
   - Add `ddrayne/openclaw-homeassistant` as an "Integration"
   - Download "OpenClaw Voice Assistant"
   - Restart Home Assistant

6. **Re-add the integration**
   - Go to **Settings > Devices & Services > Add Integration**
   - Search for "OpenClaw Voice Assistant"
   - Enter your Gateway connection details (same host, port, and token as before)

7. **Update voice assistant pipelines**
   - Go to **Settings > Voice assistants** and edit any pipeline that used Clawd
   - Re-select the conversation agent to the new "OpenClaw" entity
   - If you skip this, you'll get `Intent recognition engine conversation.openclaw_clawd is not found` errors

8. **Update automations and dashboards**
   - Any automations, scripts, or dashboard cards referencing old entity IDs (e.g. `sensor.clawd_*`, `binary_sensor.clawd_*`, `conversation.clawd`) need to be updated to use the new `openclaw` entity IDs

Your Gateway token and connection settings are unchanged — only the Home Assistant side needs to be reinstalled.
