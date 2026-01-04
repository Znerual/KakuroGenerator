# 🚀 Running the Kakuro Generator

This guide explains how to set up and run the Kakuro Generator with HTTPS enabled on both Windows (for testing) and Linux/Raspberry Pi (for production).

---

## 🛠️ Prerequisites

1.  **Python 3.8+** installed.
2.  **Caddy** installed:
    - **Windows**: Download [caddy.exe](https://caddyserver.com/download) and place it in the `backend/` folder.
    - **Linux**: `sudo apt install caddy`
3.  **Domain (Production only)**: Ensure your domain (e.g., `kakuro.servegame.com`) points to your IP.

---

## 💻 Windows (Local Testing)

Follow these steps to test the HTTPS setup locally on your machine.

### 1. Configure the Caddyfile
Open `backend/Caddyfile` and ensure the local block is uncommented:
```caddy
localhost:8008 {
    reverse_proxy localhost:8000
}
```

### 2. Start the Backend
Open a terminal in the `backend/` folder:
```cmd
# Set the host for OAuth/Links
set APP_HOST=https://localhost:8008

# Start the server (FastAPI)
uv run main.py
```

### 3. Start Caddy
Open a **second** terminal in the `backend/` folder:
```cmd
caddy run
```

### 4. Access the Site
Go to **`https://localhost:8008`**.
> [!NOTE]
> Since this is a local certificate, your browser will show a warning. Click **Advanced** and then **Proceed**.

---

## 🍓 Linux / Raspberry Pi (Production)

Follow these steps for the final deployment on your Pi.

### 1. Configure the Caddyfile
Open `backend/Caddyfile` and set it for production:
```caddy
kakuro.servegame.com {
    reverse_proxy localhost:8000
}
```

### 2. Set Environment Variables
It is recommended to use a `.env` file in the `backend/` directory:
```bash
APP_HOST=https://kakuro.servegame.com
```

### 3. Start the Backend
Run the server using `uv` (or your preferred manager) in the `backend/` folder:
```bash
export APP_HOST=https://kakuro.servegame.com
uv run main.py
```

### 4. Start Caddy
Run Caddy as a service (recommended) or manually:
```bash
sudo caddy run --config Caddyfile
```

---

## 🛰️ Network Setup (Critical for Pi)

For the Raspberry Pi to be reachable from the internet, you **must** configure your router:

1.  **Port Forwarding**: Forward Port **80** (HTTP) and Port **443** (HTTPS) to your Raspberry Pi's local IP.
2.  **FastAPI Port**: You do **not** need to forward port 8000. Caddy handles the external traffic and talks to FastAPI internally.

---

## ❓ Troubleshooting

### SSL_ERROR_RX_RECORD_TOO_LONG
This happens if you try to access `https://localhost:8000` (the backend) directly. **Always** use the Caddy port: **`https://localhost:8008`** (local) or **`https://yourdomain.com`** (production).

### Error: listen tcp 127.0.0.1:2019: bind: address already in use
On Linux/Raspberry Pi, Caddy often starts automatically as a system service. If you try to run `caddy run` manually, they will conflict on the admin port (2019).
- **Solution 1 (Recommended)**: Use the system service instead:
  ```bash
  sudo systemctl stop caddy
  caddy run --config Caddyfile
  ```
- **Solution 2**: Use `caddy reload` to update the background service:
  ```bash
  sudo cp Caddyfile /etc/caddy/Caddyfile
  sudo systemctl reload caddy
  ```

### OAuth Redirect Mismatch
Ensure `APP_HOST` in your environment matches the domain you are using, as this is used to generate the redirect URLs for Google/Facebook login.
