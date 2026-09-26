import 'dart:js_interop';

@JS('installVoterFinder')
external JSPromise<JSBoolean> _installVoterFinder();

@JS('isVoterFinderStandalone')
external JSBoolean _isVoterFinderStandalone();

bool get isPwaStandalone => _isVoterFinderStandalone().toDart;

Future<bool> promptPwaInstall() async => (await _installVoterFinder().toDart).toDart;
