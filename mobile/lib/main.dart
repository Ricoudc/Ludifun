import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/app.dart';
import 'core/config.dart';
import 'core/session.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final savedApiUrl = serverSettingsEnabled ? await readSavedApiUrl() : null;
  runApp(
    ProviderScope(
      overrides: [savedApiUrlProvider.overrideWithValue(savedApiUrl)],
      child: const LudifunApp(),
    ),
  );
}
