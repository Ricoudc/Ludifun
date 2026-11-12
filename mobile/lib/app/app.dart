import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'router.dart';
import 'theme.dart';

class LudifunApp extends ConsumerWidget {
  const LudifunApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => MaterialApp.router(
    title: 'Ludifun',
    theme: buildTheme(),
    routerConfig: ref.watch(routerProvider),
    locale: const Locale('fr'),
    supportedLocales: const [Locale('fr')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    debugShowCheckedModeBanner: false,
  );
}
