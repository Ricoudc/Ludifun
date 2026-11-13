import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/display.dart';
import 'router.dart';
import 'theme.dart';

class LudifunApp extends ConsumerWidget {
  const LudifunApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Affichage choisi sur ce téléphone (§5.94) : taille du texte, lecture facile, contraste.
    final display = ref.watch(displayProvider).value ?? const DisplaySettings();
    return MaterialApp.router(
      title: 'Ludifun',
      theme: applyDisplay(buildTheme(), display),
      builder: (context, child) => withTextSize(context, display, child ?? const SizedBox()),
      routerConfig: ref.watch(routerProvider),
      locale: const Locale('fr'),
      supportedLocales: const [Locale('fr')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      debugShowCheckedModeBanner: false,
    );
  }
}
