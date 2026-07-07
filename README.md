# XRTourGuide

<div align="center">
<img src="./assets/logo.png" width=20% heigth=20%>
<br><br>

![XRTourGuide](https://img.shields.io/badge/XR-TourGuide-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![FUTURAL](https://img.shields.io/badge/EU-FUTURAL-yellow)

**Guiding Real-Life Experiences with XR Content**

*Enriching reality with immersive media insights using Extended Reality (XR) and Artificial Intelligence (AI) to empower rural communities.*

[Website](https://isislab-unisa.github.io/XRTourGuide/) • [FUTURAL Project](https://futural-project.eu/it/)

</div>

---

## 📖 About

**XRTourGuide** is an innovative sub-project of the EU-funded [FUTURAL initiative](https://futural-project.eu/it/), focused on creating immersive virtual tours that enrich rural communities and enhance cultural heritage preservation. By combining Extended Reality (XR) technologies with Artificial Intelligence, XRTourGuide empowers local communities to create, share, and experience interactive tours of their cultural landmarks, natural sites, and historical treasures.

### The Challenge

Many rural regions rich in cultural heritage face significant obstacles:
- **Limited Accessibility**: Cultural sites struggle to remain open due to staff shortages and deteriorating infrastructure
- **Insufficient Services**: Lack of basic visitor amenities discourages tourism
- **Low Visibility**: Weak regional branding and promotional efforts keep areas "off the map"
- **Poor Information Dissemination**: Historical and practical information about sites is fragmented and hard to find

### Our Solution

XRTourGuide provides an online platform that enables communities to create and share immersive XR virtual tours, transforming how people explore and engage with rural territories. The platform combines:
- **Web-based Authoring Tools** for easy content creation
- **Mobile Applications** for discovering and experiencing tours
- **AI-Powered Visual Recognition** to trigger contextual information
- **Community Co-Creation** through active participation of local residents and organizations

---

## Key Features

### Extended Reality (XR)
Augment real-world views with interactive digital content, creating immersive experiences that blend physical and digital worlds.

### AI-Powered Visual Recognition
Automatically identify objects, artwork, buildings, and natural features to trigger relevant multimedia content.

### Multimodal Content Support
- Text descriptions
- Audio narratives
- Video presentations
- High-resolution images
- Interactive 3D models

### ☁️ Cloud-Native Architecture
Scalable, accessible Django-based web platform built for reliability and performance.

### Multi-Language Support
Make cultural content accessible to international audiences with comprehensive language support.

---

## Use Cases

XRTourGuide is being piloted in the **Bussento, Lambro, and Mingardo** rural communities:

### **Nilus Trail**
Highlighting the historical route of Saint Nilus, showcasing art, nature, and faith landmarks in the Byzantine Cilento (UNESCO World Heritage Site).

### **Morigerati Heritage**
Featuring the Ethnographic Museum's collection, emphasizing local traditions and targeting diverse audiences.

### **MushroomMate**
Identifying local mushroom species and sharing traditional recipes, promoting food culture and knowledge transfer.

---

## Project Structure

```
XRTourGuide/
├── AI_classification/       # AI models for visual recognition and image classification
├── community_server/        # Backend server for community features
├── mobile/                  # Mobile application (multi-platform)
├── pmtiles-server/          # Map tiles server for geographic data
├── xr_tour_guide/           # Core XR tour guide platform (Django)
├── LICENSE                  # MIT License
└── README.md                # Project documentation
```

---

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Git

### Quick Start

1. **Clone the repository**
```bash
git clone https://github.com/isislab-unisa/XRTourGuide.git
cd XRTourGuide
```
2. **Configure environment variables**

Create a `.env` file in xr_tour_guide:

```bash
# Database Configuration
DB_NAME=xrtourguide
DB_USER=your_admin
DB_PASSWORD=password
DB_HOST=db
DB_PORT=3306

# Django settings
SECRET_KEY=Django_secret
SITE_ID=1
FORCE_SCRIPT_NAME="/"

# MinIO
MINIO_ROOT_USER=root_user
MINIO_ROOT_PASSWORD=password
AWS_STORAGE_BUCKET_NAME="bucket-name"
AWS_S3_ENDPOINT_URL=http://minio:9000

# Email
EMAIL_HOST_PASSWORD=password
EMAIL_HOST_USER=your_email

# Google
GOOGLE_CLIENT_ID=client_id
GOOGLE_CLIENT_SECRET=secret

# Email Certbot
EMAIL_CERTBOT=your_email

# Redis and Celery endpoint 
CELERY_BROKER_URL=redis://redis:6379/0
REDIS_URL=redis://redis:6379

# Endpoint: AI train, AI inference, Django webhook, pmtiles server
CALLBACK_ENDPOINT=http://web:8001/complete_build/
TRAIN_ENDPOINT=http://ai_training:8090/train_model
INFERENCE_ENDPOINT=http://ai_inference:8050/inference
INFERENCE_CACHE_CLEAR_ENDPOINT=http://ai_inference:8050/cache/clear
PMTILES_URL=http://pmtiles-server:8081/extract

#Community server
COMMUNITY_SERVER=your_domain_name:8002

#Your domain
DOMAIN=https://yout_domain/ #the final slash is mandatory
```

Create a `.env` file in community_server:
Check [community_server .env](/community_server/README.md#quick-start)

Add a map of your region in pmtiles format in ```pmtiles-server/maps ```

> 💡 **Tip:** Generate a secure secret key with: `openssl rand -hex 32`

3. **Start all services**
```bash
cd community-server
docker compose up -d --build
cd ../xr_tour_guide
docker compose up -d --build
```

That's it! The platform will be available at the configured ports.

---

## Contributing

We welcome contributions from the community! Whether you're fixing bugs, adding features, or improving documentation, your help is appreciated.

### How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## Impact & Goals

### Expected Outcomes
- **Boost Tourism**: Increase year-round visitor flow with engaging, immersive tours
- **Community Engagement**: Raise cultural awareness and encourage citizen participation
- **Economic Growth**: Generate local job opportunities in content creation and tourism
- **Sustainability**: Support sustainable tourism and preserve cultural/natural heritage

---

## 👥 Partners

XRTourGuide is a collaborative effort bringing together:

- **[Università degli Studi di Salerno (UNISA)](https://www.unisa.it/)**
- **[ISISLab](https://www.isislab.it)** - Expertise in Cloud/Edge Computing, AI, VR, and project coordination
- **[Picaresque S.R.L.](https://tech.picaresquestudio.com/)** - Specialists in historical/serious games and software development
- **[Comunità Montana Bussento Lambro e Mingardo (CMBLM)](https://www.cmbussento.it/)** - Pilot rural community partner

### Part of FUTURAL

XRTourGuide is a sub-project of [FUTURAL](https://futural-project.eu/it/), an EU-funded initiative producing innovative, community-driven solutions to address key social, environmental, and financial challenges in rural areas across Europe.

---

## License

Shield: [![CC BY-NC 4.0][cc-by-nc-shield]][cc-by-nc]

This work is licensed under a
[Creative Commons Attribution-NonCommercial 4.0 International License][cc-by-nc].

[![CC BY-NC 4.0][cc-by-nc-image]][cc-by-nc]

[cc-by-nc]: https://creativecommons.org/licenses/by-nc/4.0/
[cc-by-nc-image]: https://licensebuttons.net/l/by-nc/4.0/88x31.png
[cc-by-nc-shield]: https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg


---

## Contact & Resources

- **Project Website**: [isislab-unisa.github.io/XRTourGuide](https://isislab-unisa.github.io/XRTourGuide/)
- **FUTURAL Project**: [futural-project.eu](https://futural-project.eu/it/)
- **Research Group**: [ISISLab - UNISA](https://www.isislab.it/)
- **GitHub Issues**: [Report bugs or request features](https://github.com/isislab-unisa/XRTourGuide/issues)

</div>