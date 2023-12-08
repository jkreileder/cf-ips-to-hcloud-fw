# Update Hetzner Cloud Firewall Rules with Current Cloudflare IPs

## Configuration

```yaml
- token: cHJvamVjdGF0b2tlbg # project a
  firewalls:
    - ICMP, SSH IPv6
    - HTTPS
- token: cHJvamVjdGJ0b2tlbg # project b
  firewalls:
    - Default
```
