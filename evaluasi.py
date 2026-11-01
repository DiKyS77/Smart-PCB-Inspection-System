"""Evaluasi akurasi model pada data uji berlabel."""
import argparse
from pathlib import Path

import yaml
import torch
from ultralytics import YOLO


def evaluate(model_path, data):
    model_path = Path(model_path).resolve()
    model = YOLO(str(model_path))
    names = yaml.safe_load(Path(data).read_text(encoding='utf-8'))['names']
    names = dict(enumerate(names)) if isinstance(names, list) else names
    if model.names != names:
        raise ValueError('Urutan kelas model dan label dataset berbeda; evaluasi dibatalkan.')
    metrics = model.val(data=data, split='test', plots=False)
    return {
        'map50': round(float(metrics.box.map50) * 100, 2),
        'map50_95': round(float(metrics.box.map) * 100, 2),
        'precision': round(float(metrics.box.mp) * 100, 2),
        'recall': round(float(metrics.box.mr) * 100, 2),
    }


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default=str(root / 'best.pt'))
    parser.add_argument('--baseline', help='Model before optimization, tested on the same data')
    parser.add_argument('--data', default=str(root / 'data.yaml'))
    args = parser.parse_args()
    torch.set_num_threads(min(4, torch.get_num_threads()))
    current = evaluate(args.model, args.data)
    baseline = evaluate(args.baseline, args.data) if args.baseline else None
    for key, value in current.items():
        suffix = f' (perubahan {value - baseline[key]:+.2f} poin)' if baseline else ''
        print(f'{key}: {value:.2f}%{suffix}')


if __name__ == '__main__':
    main()
