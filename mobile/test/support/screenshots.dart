import 'dart:io';
import 'dart:ui' show ImageByteFormat;

import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Captures d'écran pour relire l'ergonomie (audit d'octobre 2026) :
/// `flutter test test/features --dart-define=SHOTS=/un/dossier`. Sans ce réglage, rien n'est
/// fait. Limites : les emojis s'affichent en carrés (police de test), et la courte attente de
/// la capture fait avancer les minuteries (le test du défi chronométré échoue en mode capture).
const shotsDir = String.fromEnvironment('SHOTS');

bool _fontsLoaded = false;

Future<void> _loadFonts() async {
  if (_fontsLoaded) return;
  _fontsLoaded = true;
  final material =
      '${Platform.environment['FLUTTER_ROOT'] ?? '/opt/flutter'}/bin/cache/artifacts/material_fonts';
  Future<ByteData> read(String path) async =>
      ByteData.sublistView(Uint8List.fromList(File(path).readAsBytesSync()));
  // Un texte sans police précise prend « FlutterTest » dans les tests, Roboto sur le téléphone.
  for (final family in ['Roboto', 'FlutterTest']) {
    final roboto = FontLoader(family);
    for (final style in ['Bold', 'Regular', 'Medium', 'Black', 'Italic', 'Light']) {
      roboto.addFont(read('$material/Roboto-$style.ttf'));
    }
    await roboto.load();
  }
  final icons = FontLoader('MaterialIcons')..addFont(read('$material/MaterialIcons-Regular.otf'));
  await icons.load();
}

/// Enregistre l'écran courant dans `$SHOTS/<nom>.png`, au format d'un petit téléphone
/// (360 points de large, 3 pixels par point) : un débordement à cette taille fait échouer le
/// test. `height` plus grand : toute la page défilante d'un coup.
Future<void> shot(WidgetTester tester, String name, {double height = 780}) async {
  if (shotsDir.isEmpty) return;
  await tester.runAsync(_loadFonts);
  final (size, ratio) = (tester.view.physicalSize, tester.view.devicePixelRatio);
  tester.view.physicalSize = Size(360 * 3, height * 3);
  tester.view.devicePixelRatio = 3;
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
  await tester.runAsync(() async {
    final layer = tester.binding.rootElement!.renderObject!.debugLayer! as OffsetLayer;
    final image = await layer.toImage(Offset.zero & tester.view.physicalSize);
    final bytes = await image.toByteData(format: ImageByteFormat.png);
    File('$shotsDir/$name.png')
      ..createSync(recursive: true)
      ..writeAsBytesSync(bytes!.buffer.asUint8List());
  });
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = ratio;
  await tester.pump();
}
