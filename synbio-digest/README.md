# SynBio Weekly Digest

Een applicatie die wetenschappelijke databases monitort voor nieuwe publicaties over metabolic engineering en synthetische biologie, en elke maandagochtend een digest stuurt naar abonnees.

## Wat het doet

1. **Haalt nieuwe papers op** uit:
   - PubMed (biomedische literatuur)
   - bioRxiv/medRxiv (preprints)
   - arXiv (computational biology)

2. **Filtert op relevantie** voor:
   - Metabolic pathway design
   - Protein expression systems
   - Codon optimization
   - Synthetic biology tools
   - Recombinant protein production

3. **Genereert een digest** met:
   - Titel + auteurs
   - Korte samenvatting
   - Relevantie-score
   - Link naar paper

4. **Stuurt email** elke maandagochtend 07:00

## Setup

```bash
# Clone en installeer
cd synbio-digest
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configureer
cp .env.example .env
# Edit .env met je email credentials

# Database setup
python -m app.db.init

# Test run
python -m app.main --test

# Start scheduler
python -m app.main
```

## Configuratie (.env)

```
# Email (gebruik Resend, Sendgrid, of SMTP)
EMAIL_PROVIDER=resend
RESEND_API_KEY=re_xxxxx

# Of SMTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@email.com
SMTP_PASSWORD=app-password

# Database
DATABASE_URL=sqlite:///synbio_digest.db

# Optioneel: OpenAI voor betere samenvattingen
OPENAI_API_KEY=sk-xxxxx
```

## Project Structuur

```
synbio-digest/
├── app/
│   ├── __init__.py
│   ├── main.py              # Entry point + scheduler
│   ├── config.py            # Settings
│   ├── sources/             # Paper sources
│   │   ├── __init__.py
│   │   ├── pubmed.py
│   │   ├── biorxiv.py
│   │   └── arxiv.py
│   ├── processing/          # Filtering & summarization
│   │   ├── __init__.py
│   │   ├── filter.py
│   │   └── summarize.py
│   ├── email/               # Email generation & sending
│   │   ├── __init__.py
│   │   ├── templates.py
│   │   └── sender.py
│   ├── db/                  # Database models
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── init.py
│   └── api/                 # Subscription API
│       ├── __init__.py
│       └── routes.py
├── templates/
│   └── digest.html          # Email template
├── requirements.txt
├── .env.example
└── README.md
```
