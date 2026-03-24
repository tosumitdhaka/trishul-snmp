FROM python:3.10-slim

# 1. Install only snmp tools — no mibs-downloader needed
#    Saves ~50MB and eliminates all network calls at build time
RUN apt-get update && apt-get install -y \
    snmp \
    procps \
    && rm -rf /var/lib/apt/lists/*

# 2. Copy bundled MIBs from repo (replaces download-mibs)
#    Contains 16 essential standard MIBs, version-pinned in git
COPY mibs_bundled/ /usr/share/snmp/mibs/

# 3. Configure Net-SNMP
RUN sed -i 's/^mibs :/# mibs :/' /etc/snmp/snmp.conf && \
    echo "mibdirs +/usr/share/snmp/mibs/custom" >> /etc/snmp/snmp.conf && \
    echo "mibs +ALL" >> /etc/snmp/snmp.conf

# 4. Setup App
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy Code
COPY . .

# 6. Environment Defaults
ENV MODULE_NAME="main"
ENV VARIABLE_NAME="app"
ENV PORT=8000

# 7. Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
