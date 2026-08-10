# NanoDet person detector

`object_detection_nanodet_2022nov.onnx` is the FP32 NanoDet object-detection
model published by the OpenCV Model Zoo:
https://github.com/opencv/opencv_zoo/tree/main/models/object_detection_nanodet

Exact upstream weight:
https://github.com/opencv/opencv_zoo/blob/main/models/object_detection_nanodet/object_detection_nanodet_2022nov.onnx

The model is pretrained on COCO; this project performs no training or
fine-tuning and uses only COCO class 0 (`person`). The model directory in the
OpenCV Model Zoo is licensed under Apache License 2.0; the exact upstream
license text is included as `NANODET_LICENSE`.

SHA-256:
`4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186`
