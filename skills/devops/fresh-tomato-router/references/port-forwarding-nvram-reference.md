# Port Forwarding NVRAM Reference — Discovery Session 2026-07-13

## Raw nvram.portforward value

Extracted from `/forward-basic.asp` on a FreshTomato 2026.3 Asus RT-N66U router:

```
portforward': '1<1<<14001<<192.168.1.36<Esther App 1>1<1<<14002<<192.168.1.36<Esther App 2>1<1<<14007<<192.168.1.36<Esther Health>1<1<<14004<<192.168.1.36<Esther Inbox>0<1<<11990<990<192.168.1.36<Esther SFTP>1<1<<11022<22<192.168.1.36<Esther SSH>1<1<<12001<<192.168.1.47<Joseph App 1>1<1<<12002<<192.168.1.47<Joseph App 2>0<1<<20:21<<192.168.1.47<Joseph FTP>0<1<<43000:44000<<192.168.1.47<Joseph FTP pass port>1<1<<80<<192.168.1.47<Joseph HTTP>1<1<<443<<192.168.1.47<Joseph HTTPS>1<1<<12007<<192.168.1.47<Joseph Health>1<1<<12004<<192.168.1.47<Joseph Inbox>0<1<<990<<192.168.1.47<Joseph SFTP>1<1<<22<<192.168.1.47<Joseph SSH>1<1<<13001<<192.168.1.44<Moses App 1>1<1<<13002<<192.168.1.44<Moses App 2>1<1<<13007<<192.168.1.44<Moses Health>1<1<<13004<<192.168.1.44<Moses Inbox>1<1<<10022<22<192.168.1.44<Moses SSH>'
```

## Parsed Rules

### Esther (192.168.1.36) — 6 rules
| # | Enabled | Proto | Ext Port | Int Port | Target | Name |
|---|---------|-------|----------|----------|--------|------|
| 1 | ✅ | TCP | 14001 | 14001 | .36 | Esther App 1 |
| 2 | ✅ | TCP | 14002 | 14002 | .36 | Esther App 2 |
| 3 | ✅ | TCP | 14007 | 14007 | .36 | Esther Health |
| 4 | ✅ | TCP | 14004 | 14004 | .36 | Esther Inbox |
| 5 | ❌ | TCP | 11990 | 990 | .36 | Esther SFTP |
| 6 | ✅ | TCP | 11022 | 22 | .36 | Esther SSH |

### Joseph (192.168.1.47) — 10 rules
| # | Enabled | Proto | Ext Port | Int Port | Target | Name |
|---|---------|-------|----------|----------|--------|------|
| 1 | ✅ | TCP | 12001 | 12001 | .47 | Joseph App 1 |
| 2 | ✅ | TCP | 12002 | 12002 | .47 | Joseph App 2 |
| 3 | ❌ | TCP | 20:21 | 20:21 | .47 | Joseph FTP |
| 4 | ❌ | TCP | 43000:44000 | 43000:44000 | .47 | Joseph FTP pass port |
| 5 | ✅ | TCP | 80 | 80 | .47 | **Joseph HTTP** |
| 6 | ✅ | TCP | 443 | 443 | .47 | **Joseph HTTPS** |
| 7 | ✅ | TCP | 12007 | 12007 | .47 | Joseph Health |
| 8 | ✅ | TCP | 12004 | 12004 | .47 | Joseph Inbox |
| 9 | ❌ | TCP | 990 | 990 | .47 | Joseph SFTP |
| 10 | ✅ | TCP | 22 | 22 | .47 | **Joseph SSH** |

### Moses (192.168.1.44) — 5 rules
| # | Enabled | Proto | Ext Port | Int Port | Target | Name |
|---|---------|-------|----------|----------|--------|------|
| 1 | ✅ | TCP | 13001 | 13001 | .44 | Moses App 1 |
| 2 | ✅ | TCP | 13002 | 13002 | .44 | Moses App 2 |
| 3 | ✅ | TCP | 13007 | 13007 | .44 | Moses Health |
| 4 | ✅ | TCP | 13004 | 13004 | .44 | Moses Inbox |
| 5 | ✅ | TCP | 10022 | 22 | .44 | Moses SSH |

## Key Finding

The **Joseph server had moved IP** from `.47` to `.48`. The port forwarding rules still pointed to `.47` which was unreachable ("No route to host"). All Joseph rules needed updating from `192.168.1.47` → `192.168.1.48`.

## FreshTomato Discovery Notes

- **Firmware:** FreshTomato 2026.3 on Asus RT-N66U
- **HTTPS port:** 8443
- **Authentication:** HTTP Basic Auth, username is `root` (not `admin`)
- **Page `/forward.asp`** returns 500 Read error — use `/forward-basic.asp` instead
- **Navigation pattern:** `/{category}-{page}.asp` where category comes from the nav tree in `tomato.js`
- **DMZ:** Disabled (dmz_enable=0, dmz_ipaddr=0)
- **shell.cgi** can execute arbitrary commands as root on the router
