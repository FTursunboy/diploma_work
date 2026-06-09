# Cloudflare Origin SSL

Do not commit real certificate or private key files.

For `meros-ai.tj`, Nginx expects these files on the server:

```text
storage/nginx/certs/meros-ai.tj.pem
storage/nginx/certs/meros-ai.tj.key
```

Create a new certificate in Cloudflare:

1. Open `SSL/TLS -> Origin Server -> Create Certificate`.
2. Add hostnames:
   - `meros-ai.tj`
   - `*.meros-ai.tj`
3. Save the generated Origin Certificate and Private Key.
4. Set Cloudflare SSL/TLS mode to `Full (strict)`.

Install it on the server:

```bash
cd /root/diploma_work
bash scripts/install_cloudflare_origin_cert.sh
docker compose ps
```

The `book-parser-nginx` container should be `Up`, not `Restarting`.
