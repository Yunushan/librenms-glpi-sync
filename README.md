# LibreNMS → GLPI Sync

GitHub-ready project to import **LibreNMS device availability and metadata into GLPI** with a simple Python sync job and a systemd timer.

This project is designed for people who want a practical first version quickly:

- pull devices from LibreNMS
- pull 24h / 7d / 30d / 1y availability
- create or update GLPI assets automatically
- keep state in a JSON file to avoid duplicate imports
- preserve any existing GLPI comment text and only refresh the sync block
- run manually, in dry-run mode, or every 15 minutes with systemd

## What it writes into GLPI

For each LibreNMS device, the script writes a sync block into the GLPI asset comment containing:

- device ID
- hostname
- sysName
- sysDescr
- LibreNMS type
- hardware
- version
- location
- current status
- status reason
- availability for 24h / 7d / 30d / 1y
- last sync timestamp
- optional LibreNMS device URL

## Default object mapping

By default, the script maps LibreNMS device types like this:

- `server` → `Computer`
- `network` → `NetworkEquipment`
- `firewall` → `NetworkEquipment`
- anything else → `NetworkEquipment`

You can change that with `GLPI_TYPE_MAP` and `GLPI_DEFAULT_ITEMTYPE` in the env file.

---

## Project layout

```text
librenms-glpi-sync/
├── .env.example
├── .gitignore
├── install.sh
├── LICENSE
├── README.md
├── requirements.txt
├── sync.py
├── scripts/
│   ├── test_glpi_api.sh
│   └── test_librenms_api.sh
└── systemd/
    ├── librenms-glpi-sync.service
    └── librenms-glpi-sync.timer
```

---

## Requirements

- Ubuntu 22.04 or 24.04
- Python 3.10+
- GLPI with Legacy REST API enabled
- LibreNMS API token
- A GLPI account that can create and update the target asset types

---

## GLPI preparation

In GLPI:

1. Go to **Setup → General → API**.
2. Enable **API**.
3. Enable **Legacy REST API**.
4. Enable either:
   - **login with credentials**, or
   - **login with external token**
5. Create a dedicated user such as `librenms-sync`.
6. Give it the permissions required to create and update the item types you want to manage.

### Recommended auth choice

Use this first if you want the least friction:

```env
GLPI_AUTH_METHOD=basic
GLPI_APP_TOKEN=your_app_token_if_glpi_requires_it
GLPI_PROFILE_ID=your_profile_id_if_the_user_has_multiple_profiles
GLPI_USERNAME=librenms-sync
GLPI_PASSWORD=your_password
```

If you prefer tokens later:

```env
GLPI_AUTH_METHOD=token
GLPI_USER_TOKEN=your_user_token
GLPI_APP_TOKEN=your_app_token_if_required
```

---

## LibreNMS preparation

Create an API token in LibreNMS and put it in the env file:

```env
LIBRENMS_TOKEN=replace_with_librenms_api_token
```

---

## Fast install

### 1) Extract the project

```bash
unzip librenms-glpi-sync.zip
cd librenms-glpi-sync
```

### 2) Run the installer

```bash
sudo ./install.sh
```

This will:

- install the files into `/opt/librenms-glpi-sync`
- create a virtual environment
- install Python dependencies
- create `/etc/librenms-glpi-sync.env` from `.env.example` if it does not exist
- install the systemd service and timer files

### 3) Edit the env file

```bash
sudo nano /etc/librenms-glpi-sync.env
```

Minimum settings:

```env
LIBRENMS_URL=https://librenms.example.com
LIBRENMS_TOKEN=replace_with_librenms_api_token

GLPI_URL=https://glpi.example.com
GLPI_VERIFY_TLS=true
GLPI_AUTH_METHOD=basic
GLPI_APP_TOKEN=your_app_token_if_glpi_requires_it
GLPI_PROFILE_ID=
GLPI_USERNAME=librenms-sync
GLPI_PASSWORD=replace_with_glpi_password

GLPI_ENTITY_ID=1
STATE_FILE=/var/lib/librenms-glpi-sync/state.json
```

If your GLPI API configuration has an application token set, you must pass `GLPI_APP_TOKEN` even when using `GLPI_AUTH_METHOD=basic`.
If the GLPI user has multiple profiles, set `GLPI_PROFILE_ID` so the sync switches into the profile that has asset create/update rights before processing devices.
If `GLPI_ENTITY_ID` is set, the sync changes the active GLPI entity to that ID before searching or creating assets.

If you are testing against a hostname/IP with a certificate mismatch:

```env
GLPI_VERIFY_TLS=false
```

Use that only for testing or when you fully understand the TLS risk.

---

## Validation tests

### Test LibreNMS API

```bash
sudo /opt/librenms-glpi-sync/scripts/test_librenms_api.sh
```

### Test GLPI API

```bash
sudo /opt/librenms-glpi-sync/scripts/test_glpi_api.sh
```

If GLPI works, you should see a `session_token`.

---

## First sync: one device only

Before importing everything, test one host:

```bash
sudo bash -c 'set -a; source /etc/librenms-glpi-sync.env; ONLY_HOST=your-device-hostname /opt/librenms-glpi-sync/venv/bin/python /opt/librenms-glpi-sync/sync.py'
```

What to expect:

- one object is created or updated in GLPI
- a comment block appears with availability data
- the mapping is saved to the JSON state file

---

## Full sync

```bash
sudo bash -c 'set -a; source /etc/librenms-glpi-sync.env; /opt/librenms-glpi-sync/venv/bin/python /opt/librenms-glpi-sync/sync.py'
```

---

## Dry-run mode

To verify behavior without writing changes:

```bash
sudo bash -c 'set -a; source /etc/librenms-glpi-sync.env; DRY_RUN=true /opt/librenms-glpi-sync/venv/bin/python /opt/librenms-glpi-sync/sync.py'
```

---

## Enable the timer

```bash
sudo systemctl enable --now librenms-glpi-sync.timer
sudo systemctl list-timers | grep librenms-glpi-sync
```

Manual run through systemd:

```bash
sudo systemctl start librenms-glpi-sync.service
sudo journalctl -u librenms-glpi-sync.service -n 100 --no-pager
```

---

## Main environment variables

### Required

```env
LIBRENMS_URL=
LIBRENMS_TOKEN=
GLPI_URL=
GLPI_AUTH_METHOD=basic
```

### Required for basic auth

```env
GLPI_USERNAME=
GLPI_PASSWORD=
```

### Required when GLPI API enforces app tokens

```env
GLPI_APP_TOKEN=
```

### Required for token auth

```env
GLPI_USER_TOKEN=
```

### Useful optional values

```env
ONLY_HOST=
GLPI_PROFILE_ID=
GLPI_ENTITY_ID=1
GLPI_DEFAULT_ITEMTYPE=NetworkEquipment
GLPI_TYPE_MAP=server=Computer,network=NetworkEquipment,firewall=NetworkEquipment
GLPI_VERIFY_TLS=true
LIBRENMS_DEVICE_URL_TEMPLATE=https://librenms.example.com/device/device={device_id}/
DRY_RUN=false
PRESERVE_EXISTING_COMMENT=true
COMMENT_MARKER=LibreNMS sync
COMMENT_INCLUDE_RAW_JSON=false
LOG_LEVEL=INFO
REQUEST_TIMEOUT=30
```

---

## How duplicate avoidance works

The script uses two methods:

1. a local state file that maps LibreNMS `device_id` to the GLPI object ID
2. a name lookup fallback when the state entry is missing

For best long-term results, you can later add a GLPI uniqueness rule or custom fields.

---

## How comments are handled

The sync block is wrapped like this:

```text
[LibreNMS sync START]
...
[LibreNMS sync END]
```

If `PRESERVE_EXISTING_COMMENT=true`, the script keeps your existing comment text and only replaces the managed block.

If `PRESERVE_EXISTING_COMMENT=false`, the script replaces the whole comment field with the sync block.

---

## Common problems

### 1) TLS or certificate mismatch

If you test GLPI with `https://127.0.0.1` or an IP that is not present in the certificate SAN, API calls can fail TLS validation.

Solutions:

- use the real GLPI hostname from the certificate
- or temporarily set:

```env
GLPI_VERIFY_TLS=false
```

### 2) GLPI user token invalid

If token mode fails, switch to basic mode first:

```env
GLPI_AUTH_METHOD=basic
```

Once the sync is working, revisit token auth.

### 3) HTTP 400 on `initSession`

This usually means GLPI rejected the login request before the sync even started.

Check these first:

- if GLPI API is configured with an application token, set `GLPI_APP_TOKEN` even in basic auth mode
- if GLPI disables credential login, change to `GLPI_AUTH_METHOD=token`
- run `sudo /opt/librenms-glpi-sync/scripts/test_glpi_api.sh` and confirm the active profile and entity are the ones you expect

### 4) `ERROR_GLPI_ADD` while creating `Computer` or `NetworkEquipment`

This means GLPI core rejected the asset creation request.

Check these first:

- `GLPI_PROFILE_ID` points to a profile that can create and update assets through the API
- the GLPI user can create that asset type in the target entity
- `GLPI_ENTITY_ID` points to the entity where the user has rights
- `files/_logs` on the GLPI server for the exact core-side validation error

The sync now switches the active profile and active entity before processing and exits with a non-zero status if any device fails.

### 5) Device gets imported into the wrong GLPI type

Edit:

```env
GLPI_TYPE_MAP=server=Computer,network=NetworkEquipment,firewall=NetworkEquipment
```

### 6) You only want one device while testing

Use:

```env
ONLY_HOST=hostname-or-sysName-or-device_id
```

or override it for a single run:

```bash
ONLY_HOST=core-sw-01 ...
```

---

## GitHub usage

Recommended first push:

```bash
git init
git add .
git commit -m "Initial commit"
```

Do not commit your real env file. Keep secrets only in:

```text
/etc/librenms-glpi-sync.env
```

---

## Next improvements you can add later

- store availability in GLPI custom fields instead of the comment field
- add a direct GLPI external link back to the LibreNMS device page
- add LibreNMS alert transport into GLPI for ticket creation
- split device classes more precisely between `Computer`, `NetworkEquipment`, `Appliance`, and custom asset definitions

---

## Safe rollout order

1. validate both APIs
2. run a dry-run
3. import one device with `ONLY_HOST`
4. verify GLPI output
5. run full sync manually
6. enable the timer

---

## Notes

This project intentionally keeps the first version simple and supportable. It imports the **availability data** into GLPI, but leaves the live **LibreNMS map/dashboard** in LibreNMS, which is the cleaner architecture for most environments.
