# Trishul SNMP - Deployment Guide

## 🚀 Two Deployment Options

### Option 1: Vite Development Mode (Advanced)
**Pros:** Hot Module Reload, modern dev experience  
**Cons:** May interfere with dynamic HTML loading

```bash
docker-compose up -d
```

### Option 2: Simple Nginx Mode (Recommended)
**Pros:** No build system interference, pure static serving  
**Cons:** No HMR, need manual refresh

```bash
# Stop Vite version
docker-compose down

# Use simple mode
docker-compose -f docker-compose.simple.yml up -d
```

---

## 📝 Simple Mode Details

### Architecture
- **nginx:alpine** - Lightweight web server
- Direct file serving from `frontend/src/`
- No build step, no node_modules
- API proxy to backend:8000

### File Structure
```
frontend/src/
├── index.html          # Main entry
├── dashboard.html      # Module HTMLs
├── simulator.html
├── js/
│   ├── app.js         # Main app
│   ├── core/          # Core modules
│   └── components/    # UI components
├── css/
│   └── style.css      # Styles
└── img/               # Images
```

### Development Workflow
1. Edit files in `frontend/src/`
2. Refresh browser (Ctrl+F5 for hard refresh)
3. Changes appear immediately (nginx volume mounted)

---

## 🔧 Switching Modes

### Vite → Simple
```bash
docker-compose down
docker-compose -f docker-compose.simple.yml up -d
```

### Simple → Vite
```bash
docker-compose -f docker-compose.simple.yml down
docker-compose up -d
```

---

## 🐛 Troubleshooting

### Container Not Found Issue?
**Solution:** Use simple mode - Vite's HMR may interfere

### Changes Not Appearing?
- Simple mode: Hard refresh (Ctrl+F5)
- Vite mode: Should auto-refresh

### Port Already in Use?
```bash
# Find and kill process
sudo lsof -i :8080
sudo kill -9 <PID>
```

### Clear Everything
```bash
docker-compose down -v
docker system prune -f
```

---

## 📊 Performance Comparison

| Metric | Simple Mode | Vite Mode |
|--------|------------|----------|
| Build time | None | ~5s |
| Container size | 25MB | 450MB |
| Startup time | <1s | ~3s |
| HMR | ❌ | ✅ |
| Stability | ✅✅✅ | ⚠️ |

---

## 🎯 Recommendation

**Use Simple Mode** for:
- Production
- Stable development
- Dynamic HTML loading
- Docker environments

**Use Vite Mode** for:
- Fast iteration on JS/CSS
- Component development
- When HMR is critical

---

## 📝 Notes

- Simple mode serves files directly from `frontend/src/`
- Changes reflect immediately with browser refresh
- No node_modules needed in simple mode
- Both modes proxy `/api` to backend
