#!/usr/bin/env bash
set -euo pipefail

WG_CONF=/etc/wireguard/wg0.conf
SERVER_PUBLIC_KEY=$(cat /etc/wireguard/server_public.key)
SERVER_IP="${SERVER_IP:-YOUR_SERVER_IP}"
BACKUP="${WG_CONF}.bak.$(date +%Y%m%d%H%M%S)"
cp "$WG_CONF" "$BACKUP"

create_friend() {
  local number="$1"
  local friend_ip="10.66.66.${number}"
  local output="/root/friend${number}-clash.yaml"
  local client_private_key client_public_key

  if grep -qF "AllowedIPs = ${friend_ip}/32" "$WG_CONF"; then
    echo "friend${number}: address already exists, skipped"
    return
  fi

  client_private_key=$(wg genkey)
  client_public_key=$(printf '%s' "$client_private_key" | wg pubkey)

  cat >> "$WG_CONF" <<EOF

[Peer]
PublicKey = ${client_public_key}
AllowedIPs = ${friend_ip}/32
EOF

  cat > "$output" <<EOF
mixed-port: 7890
allow-lan: false
mode: rule
ipv6: false

dns:
  enable: true
  ipv6: false
  nameserver:
    - 1.1.1.1
    - 8.8.8.8

proxies:
  - name: US-WireGuard-${number}
    type: wireguard
    server: ${SERVER_IP}
    port: 51820
    ip: ${friend_ip}
    private-key: ${client_private_key}
    public-key: ${SERVER_PUBLIC_KEY}
    udp: true
    mtu: 1420
    remote-dns-resolve: true
    dns:
      - 1.1.1.1
      - 8.8.8.8

proxy-groups:
  - name: PROXY
    type: select
    proxies:
      - US-WireGuard-${number}

rules:
  - MATCH,PROXY
EOF
  chmod 600 "$output"
  echo "friend${number}: generated ${output}"
}

create_friend 6
create_friend 7

if ! wg-quick strip wg0 >/dev/null; then
  cp "$BACKUP" "$WG_CONF"
  echo "WireGuard syntax failed; restored backup" >&2
  exit 1
fi

chmod 600 "$WG_CONF"
systemctl restart wg-quick@wg0
systemctl is-active --quiet wg-quick@wg0

echo "WireGuard active"
wg show wg0 allowed-ips | grep -E '10\.66\.66\.(6|7)/32'
grep -H '^    ip:' /root/friend6-clash.yaml /root/friend7-clash.yaml
