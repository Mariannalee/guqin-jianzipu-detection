# Model Card

## Model

- Base model: PP-OCRv5 mobile detection
- Task: guqin jianzipu candidate-region detection
- Framework: PaddleOCR
- Checkpoint: `model/best_accuracy.pdparams`

## Training data

The current fine-tuning set contains 26 training panel images and 4 validation panel images from scanned pages of *Wuzhizhai Qinpu* in *Qinqu Jicheng*. The complete scans and annotations are not distributed in this repository.

## Validation metrics

- Precision: 0.7189
- Recall: 0.9614
- Hmean: 0.8227
- Best epoch: 8

These metrics come from a small in-domain validation set and must not be interpreted as performance on unseen editions or layouts.

## Intended use

Research assistance for locating candidate jianzipu glyph regions before human review. The model is not a semantic recognizer and does not identify strings, hui positions, fingering, or performance meaning.

## Limitations

The detector can include titles, annotations, punctuation, or scanning noise, and can split or merge glyphs incorrectly. Human verification is required. Performance may degrade on different editions, fonts, layouts, or image qualities.
