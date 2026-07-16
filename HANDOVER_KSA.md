# NazmOS KSA – Client Handover Document
## وثيقة تسليم نظام نظم

**License:** SAR 25,000 – One-time, per location  
**Version:** 2.1.0-ksa  
**Support:** 30 days WhatsApp included

---

### 1. Access URLs
- Dashboard: http://localhost:3000
- API Docs: http://localhost:8000/docs

### 2. Admin Account
Email: _____________________  
Password: _____________________  
⚠️ Change password after first login: Profile → Security

### 3. What is included
✅ Dashboard – sales, profit, KPIs – SAR  
✅ Inventory – dead stock, reorder points  
✅ Upload – CSV/Excel POS import, retail recovery mapper  
✅ Forecast – Prophet, Ramadan / Eid / National Day / White Friday  
✅ WhatsApp alerts – low stock  
✅ Arabic / English UI  
✅ Offline – all data stays on your server – PDPL compliant

**NOT included (Phase 2):**
- Baseer AI Chat – coming Q2 2027
- Mobile app
- Auto POS sync
- Cloud hosting

### 4. Daily workflow
1. Upload yesterday's sales CSV → Upload → Confirm mapping
2. Check Dashboard – sales vs yesterday
3. Check Inventory → Dead Stock – discount slow items
4. Forecast → check next 7 days before ordering – especially before Ramadan

### 5. Backup
Database: PostgreSQL in Docker volume `nazmos_postgres_data`
Backup command:
```
docker exec nazmos-postgres pg_dump -U nazmos nazmos > backup_$(date +%F).sql
```
Restore: contact support

### 6. Support
WhatsApp: +966 5X XXX XXXX  
Email: support@nazmos.sa  
Hours: Sat–Thu, 9am–6pm AST

### 7. System Requirements
- Windows 10/11 + Docker Desktop, OR Ubuntu 22.04+
- 8GB RAM, 20GB disk
- Chrome / Edge browser

### 8. Uninstall
```
docker compose down -v
```
⚠️ This deletes all data. Backup first.

---
**NazmOS – نظام – KSA Retail Intelligence**  
Riyadh • Buraidah • Jeddah
