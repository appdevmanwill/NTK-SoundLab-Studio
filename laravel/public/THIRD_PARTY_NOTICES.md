# Third-party notices

NTK SoundLab Studio is distributed under the project MIT license. The following components carry their own notices.

| Component | Bundled notices and corresponding source |
| --- | --- |
| MediaBunny 1.65.0 | [MPL-2.0 license](lib/mediabunny/LICENSE.txt) and [corresponding source notice](lib/mediabunny/NOTICE.txt) |
| ONNX Runtime Web 1.20.1 | [MIT license](lib/onnxruntime/1.20.1/LICENSE.txt), [third-party notices](lib/onnxruntime/1.20.1/ThirdPartyNotices.txt), and [pinned npm package](https://www.npmjs.com/package/onnxruntime-web/v/1.20.1) |
| Demucs browser processing code | [MIT license](lib/demucs-web/LICENSE.txt) and [upstream source](https://github.com/timcsy/demucs-web) |
| JSZip 3.10.1 | [License](lib/licenses/JSZip.txt) and [upstream source](https://github.com/Stuk/jszip/tree/v3.10.1) |
| lamejs 1.2.1 | [License](lib/licenses/lamejs.txt) and [corresponding source package](https://registry.npmjs.org/lamejs/-/lamejs-1.2.1.tgz) |

The optional HTDemucs ONNX file is supplied separately from the app packages. The loader verifies the file against the [pinned model revision](https://huggingface.co/timcsy/demucs-web-onnx/tree/92e33df61cfc9eb820272aaa62d2ef6dcf4d950d). The model repository does not declare a license in its metadata. Confirm terms with the model publisher before redistributing the weights.
