FROM python:3.10-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir cookiecutter copier cruft pyscaffold pyyaml

WORKDIR /app

COPY resources /app/resources
COPY technologies /app/technologies

RUN mkdir -p /app/technologies/cookiecutter/output \
    /app/technologies/copier/output \
    /app/technologies/cruft/output \
    /app/technologies/pyscaffold/output

RUN echo '#!/bin/bash\n\
    echo "Running CookieCutter..."\n\
    python3 technologies/cookiecutter/generate.py\n\
    echo "Running Copier..."\n\
    python3 technologies/copier/generate.py\n\
    echo "Running Cruft..."\n\
    python3 technologies/cruft/generate.py\n\
    echo "Running PyScaffold..."\n\
    python3 technologies/pyscaffold/generate.py\n\
    echo "Done!"' > /app/run_all.sh && chmod +x /app/run_all.sh

CMD ["/app/run_all.sh"]
