import 'dart:ui_web' as ui_web;

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

/// Web implementation: embeds the PDF in an <iframe>.  The browser's native
/// PDF renderer honours the `#page=N` fragment so the viewer jumps straight
/// to the matching page.
Widget buildPdfFrame(String url) => _IframeView(url: url);

class _IframeView extends StatefulWidget {
  const _IframeView({required this.url});
  final String url;

  @override
  State<_IframeView> createState() => _IframeViewState();
}

class _IframeViewState extends State<_IframeView> {
  static int _counter = 0;
  late final String _viewType;

  @override
  void initState() {
    super.initState();
    _viewType = 'pdf-frame-${_counter++}';
    ui_web.platformViewRegistry.registerViewFactory(_viewType, (int viewId) {
      final iframe = web.HTMLIFrameElement()
        ..src = widget.url
        ..style.border = 'none'
        ..style.width = '100%'
        ..style.height = '100%';
      return iframe;
    });
  }

  @override
  Widget build(BuildContext context) => HtmlElementView(viewType: _viewType);
}
