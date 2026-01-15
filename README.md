## setup

requirements:
- docker

start services:

    docker compose up -d

pull the model (one-time):

    docker exec -it ollama ollama pull qwen2.5-coder:7b

verify:

    curl http://localhost:8000/health
