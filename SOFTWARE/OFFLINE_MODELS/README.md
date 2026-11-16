# Optional offline stem model

NTK SoundLab Studio 2026.11.16.3 includes the matching ONNX Runtime Web files.

1. Use the local `htdemucs_embedded.onnx` file in this folder when available, or save the [pinned model file](https://huggingface.co/timcsy/demucs-web-onnx/resolve/92e33df61cfc9eb820272aaa62d2ef6dcf4d950d/htdemucs_embedded.onnx?download=true).
2. Open the app, choose **Offline Storage**, and select the model under **Offline stem separation**. Wait for the completion message.
3. Import an audio file and open its **2 / 4 Stem AI** controls. Choose the browser engine to run the model on the device.

The model is 180,534,758 bytes. SoundLab verifies this SHA-256 digest before saving or loading the model.

```text
e5e425c17683f163a472462eb5f5a4ffcd11c31858d57fbd0833b012d8b88077
```

On the desktop, you can also place the file in the `models` folder inside the app data directory. Keep a copy of the model file so you can reimport it after a browser data reset. Prepare hosted browser storage while the app site is reachable.

Confirm the model publisher's redistribution terms before sharing copies of the weights. [Pinned model revision](https://huggingface.co/timcsy/demucs-web-onnx/tree/92e33df61cfc9eb820272aaa62d2ef6dcf4d950d)
