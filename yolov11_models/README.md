# YOLO11 PCB Defect Detection

本目录汇总了本次 PCB 缺陷检测实验的核心代码与最佳权重，适合单独上传 GitHub。

## 文件结构

```text
github_yolo11_pcb_release/
├── README.md
├── data.yaml
├── requirements.txt
├── train_yolo_pcb.py
├── infer_pcb_defect.py
├── weights/
│   └── best.pt
└── results/
    └── smoke_test/
```

## 环境安装

建议使用 Python 3.10+。本次训练环境为 Python 3.12.3、PyTorch 2.5.1+cu124、Ultralytics 8.3.0、RTX 4090。

```bash
python -m venv .venv
source .venv/bin/activate
pip install torch==2.5.1 torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
```

CPU 环境也可以推理，但速度会慢很多。CPU 环境安装时可按 PyTorch 官网选择对应命令。

训练环境：

| item | value |
|---|---|
| GPU | NVIDIA GeForce RTX 4090, 24 GB |
| Python | 3.12.3 |
| PyTorch | 2.5.1+cu124 |
| Ultralytics | 8.3.0 |
| CUDA | cu124 |

核心训练配置：

| item | value |
|---|---|
| base model | `yolo11n.pt` |
| epochs | 200 |
| image size | 640 |
| batch | 32 |
| workers | 8 |
| device | 0 |
| optimizer | auto |
| patience | 200 |
| save_period | 1 |
| pretrained | true |
| AMP | true |
| seed | 0 |

## 单张图片推理

```bash
python infer_pcb_defect.py \
  --model weights/best.pt \
  --source /path/to/image.jpg \
  --output results/single_image \
  --conf 0.25 \
  --device 0
```

输出内容：

```text
results/single_image/
├── image.jpg
├── detections.json
└── detections.csv
```

其中图片为带检测框的可视化结果，`detections.json` 和 `detections.csv` 会记录每个检测框的类别、置信度和坐标。

## 多张图片推理

目录推理：

```bash
python infer_pcb_defect.py \
  --model weights/best.pt \
  --source /path/to/images \
  --output results/batch_images \
  --conf 0.25 \
  --device 0
```

glob 推理：

```bash
python infer_pcb_defect.py \
  --model weights/best.pt \
  --source "/path/to/images/*.jpg" \
  --output results/batch_glob \
  --conf 0.25 \
  --device 0
```

`detections.json` 的单个检测框格式如下：

```json
{
  "class_id": 3,
  "class_name": "short",
  "confidence": 0.92,
  "bbox_xyxy": [102.4, 88.1, 173.6, 156.8],
  "bbox_xywh": [102.4, 88.1, 71.2, 68.7]
}
```

## 训练复现

训练脚本默认读取本目录下的 `data.yaml`。上传 GitHub 后，可将数据集按如下结构放置：

```text
github_yolo11_pcb_release/
├── data.yaml
└── datasets/
    └── pcb_defect/
        ├── images/
        │   ├── train/
        │   ├── val/
        │   └── test/
        └── labels/
            ├── train/
            ├── val/
            └── test/
```

复现本次 200 epoch 训练可执行：

```bash
python train_yolo_pcb.py \
  --data data.yaml \
  --model yolo11n.pt \
  --epochs 200 \
  --imgsz 640 \
  --batch 32 \
  --workers 8 \
  --device 0 \
  --save-period 1 \
  --patience 200 \
  --name pcb_defect_yolo11n_full_200e
```

本次发布的最佳权重为：

```text
weights/best.pt
```

## 训练结果统计

数据集划分：

| split | images | labels | objects |
|---|---:|---:|---:|
| train | 5120 | 5120 | 10306 |
| val | 3414 | 3414 | 7009 |
| test | 2134 | 2134 | 4349 |
| total | 10668 | 10668 | 21664 |

类别：

| id | class | train objects | val objects | test objects |
|---:|---|---:|---:|---:|
| 0 | missing_hole | 1694 | 1179 | 739 |
| 1 | mouse_bite | 1725 | 1156 | 803 |
| 2 | open_circuit | 1678 | 1210 | 660 |
| 3 | short | 1657 | 1145 | 706 |
| 4 | spur | 1728 | 1143 | 765 |
| 5 | spurious_copper | 1824 | 1176 | 676 |


验证集最佳结果出现在 epoch 200：

| metric | value |
|---|---:|
| precision | 0.98358 |
| recall | 0.98978 |
| mAP50 | 0.99116 |
| mAP50-95 | 0.68318 |
| train box loss | 0.88180 |
| train cls loss | 0.41228 |
| train dfl loss | 0.90280 |
| val box loss | 1.16830 |
| val cls loss | 0.44390 |
| val dfl loss | 0.98452 |

## 测试集评估

测试集整体指标：

| metric | value |
|---|---:|
| images | 2134 |
| instances | 4349 |
| precision | 0.98412 |
| recall | 0.99252 |
| mAP50 | 0.99232 |
| mAP50-95 | 0.68979 |

测试集各类别 `mAP50-95`：

| class | mAP50-95 |
|---|---:|
| missing_hole | 0.694 |
| mouse_bite | 0.692 |
| open_circuit | 0.660 |
| short | 0.698 |
| spur | 0.686 |
| spurious_copper | 0.708 |