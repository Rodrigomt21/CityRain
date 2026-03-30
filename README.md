# CityRain

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![PyTorch](https://img.shields.io/badge/PyTorch-2.x-EE4C2C?logo=pytorch)
![YOLOv11](https://img.shields.io/badge/YOLO-v11--TWCS-00FFFF?logo=yolo)
![Edge AI](https://img.shields.io/badge/Edge%20AI-Embedded-green)
![V2X](https://img.shields.io/badge/Protocol-V2X%20%2F%20ADAS-orange)
![IMT](https://img.shields.io/badge/Instituição-IMT%20Mauá-red)

> **Edge AI system that transforms automotive and urban cameras into active meteorological sensors**, estimating rain intensity in mm/h in real time.

---

## Overview

CityRain addresses a critical gap in weather sensing: most vision-based systems only answer *"is it raining?"* — a binary output. This project moves beyond detection into **continuous quantification**, estimating rainfall intensity in **millimeters per hour (mm/h)** directly from video frames captured by existing roadside and onboard cameras.

The system targets deployment on **resource-constrained edge hardware** (dashcams, traffic cameras, embedded ADAS modules), producing a structured meteorological payload compatible with **V2X (Vehicle-to-Everything)** networks.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CityRain Pipeline                        │
├──────────────┬──────────────────────────────┬───────────────────┤
│  Input Layer │     Vision & Inference       │   Output Layer    │
│              │                              │                   │
│  Camera Feed │ ► Preprocessing              │ mm/h Estimate     │
│  (RGB Frame) │ ► YOLOv11-TWCS (CNN)        │ V2X Payload       │
│              │ ► Optical Degradation Model  │ ADAS Integration  │
│              │ ► Atmospheric Transmission   │ Dashboard/Log     │
│              │   (extinction coefficients)  │                   │
└──────────────┴──────────────────────────────┴───────────────────┘
```

### Key Components

| Layer | Description |
|---|---|
| **CNN Backbone** | Single-stage detector (YOLOv11-TWCS) optimized for edge deployment |
| **Optical Model** | Image degradation analysis based on atmospheric transmission and Beer-Lambert extinction |
| **Intensity Estimator** | Maps visual features to continuous mm/h values |
| **V2X Emulator** | Structures output as a standard meteorological data payload |
| **Calibration Module** | Validates estimates against physical rain gauges |

---

## Objectives

- **Primary**: Quantify rainfall intensity (mm/h) from camera frames with sub-meter accuracy.
- **Secondary**: Enable dynamic adjustment of braking and traction in autonomous vehicles via real-time ADAS integration.
- **Tertiary**: Leverage existing camera infrastructure (zero additional hardware cost) to extend urban weather networks.

---

## Methodology

### 1. Visual Rain Detection
Single-stage CNN (YOLO family) detects rain streaks and atmospheric haze patterns in individual frames. The model is trained on labeled datasets spanning multiple rain intensities, lighting conditions, and camera types.

### 2. Physical Intensity Estimation
Rain intensity is not inferred statistically alone — it is grounded in physics:

- **Atmospheric Transmission Model**: $I = I_0 \cdot e^{-\beta \cdot d}$, where $\beta$ is the extinction coefficient and $d$ is the optical path length.
- **Optical Degradation Metrics**: Contrast reduction, streak density, and blur kernel analysis are combined to produce a continuous intensity score.
- **Calibrated Mapping**: The visual score is mapped to mm/h using regression calibrated against co-located physical rain gauges.

### 3. Edge Optimization
- **Post-training quantization** (INT8/FP16) for reduced memory footprint.
- **Layer fusion** to minimize latency on embedded NPUs/GPUs.
- Inference benchmarked on target embedded platforms.

### 4. Validation
Ground-truth comparison between CityRain's mm/h estimates and readings from certified tipping-bucket rain gauges placed in the same monitored area.

---

## Tech Stack

| Category | Technology |
|---|---|
| **Deep Learning** | PyTorch, Ultralytics YOLOv11 |
| **Computer Vision** | OpenCV, NumPy |
| **Physical Modeling** | SciPy, custom atmospheric optics modules |
| **Edge Deployment** | ONNX Runtime, TensorRT, OpenVINO |
| **V2X / ADAS** | Custom payload serialization (JSON/Protobuf) |
| **Validation** | Pandas, Matplotlib, scikit-learn |
| **Hardware Targets** | NVIDIA Jetson, Raspberry Pi 5, generic dashcam SoCs |

---

## Project Structure

```
CityRain/
├── data/               # Datasets, annotations, and rain gauge logs
├── models/             # Model definitions and pretrained weights
├── pipeline/           # Inference pipeline and V2X payload emitter
├── physics/            # Atmospheric transmission and optical models
├── calibration/        # Rain gauge comparison and calibration scripts
├── notebooks/          # Exploratory analysis and results
├── scripts/            # Training, evaluation, and export utilities
└── tests/              # Unit and integration tests
```

---

## Authors

| Name | Role |
|---|---|
| Rodrigo Monteiro Toffoli Teixeira | Developer & Researcher |
| Guilherme Mattioli | Developer & Researcher |
| Gabriel Moreno | Developer & Researcher |
| Paulo Vespero | Developer & Researcher |

**Advisor**: Prof. Gabriel de Souza Lima

**Institution**: Centro Universitário do Instituto Mauá de Tecnologia (IMT)

---

## Citation

If you use this work, please cite:

```bibtex
@thesis{cityrain2025,
  title   = {CityRain: Edge AI for Continuous Rainfall Intensity Estimation via Vision Systems},
  author  = {Teixeira, Rodrigo M. T. and Mattioli, Guilherme and Moreno, Gabriel and Vespero, Paulo},
  school  = {Centro Universitário do Instituto Mauá de Tecnologia},
  year    = {2025},
  advisor = {Lima, Gabriel de Souza}
}
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
