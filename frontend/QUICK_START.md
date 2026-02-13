# Quick Start Guide - Trishul SNMP Frontend

⚡ Get up and running in 5 minutes!

## Prerequisites

- Docker & Docker Compose (recommended)
- OR Node.js 18+ and npm 9+ (for local development)

## Quick Start with Docker (Recommended)

### 1. Clone and Navigate
```bash
git clone https://github.com/tosumitdhaka/trishul-snmp.git
cd trishul-snmp
git checkout frontend-enhancements
```

### 2. Start Development Environment
```bash
# Build and start all services
docker-compose up --build

# Or run in background
docker-compose up --build -d
```

### 3. Access Application
- Frontend: http://localhost:8080
- Backend API: http://localhost:8000
- Default login: `admin` / `admin`

### 4. View Logs
```bash
# All services
docker-compose logs -f

# Frontend only
docker-compose logs -f frontend

# Backend only
docker-compose logs -f backend
```

### 5. Stop Services
```bash
# Stop
docker-compose stop

# Stop and remove containers
docker-compose down

# Remove everything including volumes
docker-compose down -v
```

---

## Local Development (Without Docker)

### 1. Install Dependencies
```bash
cd frontend
npm install
```

### 2. Start Backend
```bash
# In separate terminal
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### 3. Start Frontend Dev Server
```bash
cd frontend
npm run dev
```

### 4. Access
- Frontend: http://localhost:8080
- Backend: http://localhost:8000

---

## Development Workflow

### Hot Module Replacement (HMR) ⚡

Edit any file in `frontend/src/` and see changes **instantly** in browser:

```bash
# Make a change
echo 'console.log("Updated!");' >> src/js/app.js

# Browser updates automatically (< 50ms)
# No refresh needed!
```

### Available Commands

```bash
cd frontend

# Development
npm run dev          # Start dev server with HMR
npm run build        # Build for production
npm run preview      # Preview production build

# Code Quality
npm run lint         # Lint JavaScript
npm run format       # Format code with Prettier

# Analysis
npm run build:analyze  # Visualize bundle size

# Cleanup
npm run clean        # Remove dist/ and node_modules/
```

---

## Project Structure

```
frontend/
├── src/                    # Source code
│   ├── js/
│   │   ├── core/          # Core system (router, auth, store)
│   │   ├── components/    # Reusable UI components
│   │   ├── modules/       # Feature modules
│   │   └── app.js         # Entry point
│   ├── css/
│   ├── img/
│   └── index.html
├── dist/                  # Built files (gitignored)
├── node_modules/          # Dependencies (gitignored)
├── vite.config.js         # Vite configuration
├── package.json
└── Dockerfile
```

---

## Testing the Build

### Test Components

Open browser console and try:

```javascript
// Import and test Card component
const { Card } = await import('./js/components/Card.js');
const card = new Card(document.body, {
    title: 'Hello Vite!',
    icon: 'fas fa-rocket',
    content: '<p>HMR is working!</p>'
});
await card.init();

// Import and test Alert
const { Alert } = await import('./js/components/Alert.js');
Alert.show(document.body, 'Build system ready!', 'success');

// Check build info
console.log('Dev mode:', __DEV__);
console.log('Build time:', __BUILD_TIME__);
console.log('Environment:', import.meta.env.MODE);
```

### Test HMR

1. Open `frontend/src/js/app.js`
2. Add a console log: `console.log('HMR Test');`
3. Save file
4. Check browser console - should see log **without refresh**!

---

## Common Issues & Solutions

### Port 8080 Already in Use

```bash
# Find what's using port 8080
lsof -i :8080

# Kill the process
kill -9 <PID>

# Or change port in vite.config.js
```

### HMR Not Working

```bash
# Restart frontend container
docker-compose restart frontend

# Hard refresh browser
# Chrome/Edge: Ctrl+Shift+R
# Firefox: Ctrl+F5
```

### Login Screen Won't Disappear

```bash
# Clear browser storage
# F12 > Application > Clear site data

# Or clear in console
localStorage.clear();
sessionStorage.clear();
location.reload();
```

### Node Modules Issues

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### Docker Build Fails

```bash
# Clean Docker build cache
docker-compose down
docker system prune -a
docker-compose up --build
```

---

## Production Build

### Build Static Files

```bash
cd frontend
npm run build

# Output in dist/
# ├── index.html
# ├── assets/
# │   ├── vendor-[hash].js
# │   ├── core-[hash].js
# │   ├── components-[hash].js
# │   └── style-[hash].css
```

### Run Production Build

```bash
# Preview locally
npm run preview

# Or with Docker + Nginx
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up --build

# Access at http://localhost:80
```

---

## Next Steps

1. **Explore Components** - See [COMPONENT_EXAMPLES.md](./COMPONENT_EXAMPLES.md)
2. **Read Documentation** - Check [MIGRATION_PHASE1.*.md](./)
3. **Start Building** - Create your first module with components
4. **Join Development** - See [MIGRATION_STATUS.md](./MIGRATION_STATUS.md)

---

## Getting Help

- 📖 **Documentation**: See `MIGRATION_PHASE*.md` files
- 📝 **Examples**: See `COMPONENT_EXAMPLES.md`
- 🐛 **Issues**: Create GitHub issue with `frontend` label
- 💬 **Questions**: Comment on PR or issue

---

## Useful Links

- [Vite Documentation](https://vitejs.dev/)
- [Bootstrap 5 Documentation](https://getbootstrap.com/docs/5.3/)
- [ES6 Modules Guide](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules)
- [Docker Compose Documentation](https://docs.docker.com/compose/)

---

**Happy Coding! 🚀**

*If you encounter any issues, check [MIGRATION_PHASE1.4.md](./MIGRATION_PHASE1.4.md) for detailed troubleshooting.*
