FROM python:3.11-slim

# Installa Java (necessario per Nextflow)
RUN apt-get update && apt-get install -y \
    openjdk-21-jdk \
    curl \
    bash \
    && rm -rf /var/lib/apt/lists/*

# Installa Nextflow
RUN curl -s https://get.nextflow.io | bash && \
    mv nextflow /usr/local/bin/ && \
    chmod +x /usr/local/bin/nextflow

# Imposta la working directory
WORKDIR /app

# Copia e installa le dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia il progetto
COPY . .

# Comando di default
CMD ["nextflow", "run", "pipeline_docker_friendly.nf"]