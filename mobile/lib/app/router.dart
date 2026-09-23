import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/session.dart';
import '../core/storage/credentials.dart';
import '../features/analysis/analysis_screen.dart';
import '../features/capture/capture_screen.dart';
import '../features/home/child_home_screen.dart';
import '../features/lesson/lesson_screen.dart';
import '../features/link/link_screen.dart';
import '../features/link/qr_scan_screen.dart';
import '../features/parent/parent_home_screen.dart';
import '../features/parent/parent_sign_in_screen.dart';
import '../features/session/session_screen.dart';
import '../features/start/splash_screen.dart';
import '../features/start/start_screen.dart';

abstract final class Routes {
  static const splash = '/chargement';
  static const start = '/';
  static const parentSignIn = '/parent/connexion';
  static const parentRegister = '/parent/inscription';
  static const parentHome = '/parent';
  static const link = '/lier';
  static const scanQr = '/lier/qr';
  static const childHome = '/enfant';
  static const capture = '/enfant/photo';
  static String analysis(String lessonId) => '/enfant/analyse/$lessonId';
  static String lesson(String lessonId) => '/enfant/lecon/$lessonId';
  static String session(String sessionId) => '/enfant/seance/$sessionId';
}

/// Chaque espace n'est accessible qu'avec ses identifiants : le routeur renvoie vers
/// le premier lancement, l'espace parent ou l'espace enfant selon la session.
String? redirect(AsyncValue<Credentials> session, String location) {
  if (session.isLoading && !session.hasValue) return Routes.splash;
  final credentials = session.value ?? const NoCredentials();
  const signedOut = {
    Routes.start,
    Routes.parentSignIn,
    Routes.parentRegister,
    Routes.link,
    Routes.scanQr,
  };
  final target = switch (credentials) {
    NoCredentials() => signedOut.contains(location) ? location : Routes.start,
    ParentCredentials() =>
      location.startsWith(Routes.parentHome) && !signedOut.contains(location)
          ? location
          : Routes.parentHome,
    ChildCredentials() => location.startsWith(Routes.childHome) ? location : Routes.childHome,
  };
  return target == location ? null : target;
}

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier(0);
  ref.listen(sessionProvider, (_, _) => refresh.value++);
  ref.onDispose(refresh.dispose);
  final router = GoRouter(
    initialLocation: Routes.splash,
    refreshListenable: refresh,
    redirect: (context, state) => redirect(ref.read(sessionProvider), state.matchedLocation),
    routes: [
      GoRoute(path: Routes.splash, builder: (_, _) => const SplashScreen()),
      GoRoute(path: Routes.start, builder: (_, _) => const StartScreen()),
      GoRoute(path: Routes.parentSignIn, builder: (_, _) => const ParentSignInScreen()),
      GoRoute(
        path: Routes.parentRegister,
        builder: (_, _) => const ParentSignInScreen(register: true),
      ),
      GoRoute(path: Routes.parentHome, builder: (_, _) => const ParentHomeScreen()),
      GoRoute(path: Routes.link, builder: (_, _) => const LinkScreen()),
      GoRoute(path: Routes.scanQr, builder: (_, _) => const QrScanScreen()),
      GoRoute(
        path: Routes.childHome,
        builder: (_, _) => const ChildHomeScreen(),
        routes: [
          GoRoute(path: 'photo', builder: (_, _) => const CaptureScreen()),
          GoRoute(
            path: 'analyse/:id',
            builder: (_, state) => AnalysisScreen(lessonId: state.pathParameters['id']!),
          ),
          GoRoute(
            path: 'lecon/:id',
            builder: (_, state) => LessonScreen(lessonId: state.pathParameters['id']!),
          ),
          GoRoute(
            path: 'seance/:id',
            builder: (_, state) => SessionScreen(sessionId: state.pathParameters['id']!),
          ),
        ],
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});
