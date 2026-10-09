import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/session.dart';
import '../core/storage/credentials.dart';
import '../features/analysis/analysis_screen.dart';
import '../features/capture/capture_screen.dart';
import '../features/capture/text_import_screen.dart';
import '../features/home/child_home_screen.dart';
import '../features/lesson/lesson_screen.dart';
import '../features/link/link_screen.dart';
import '../features/link/qr_scan_screen.dart';
import '../features/parent/ai_settings_screen.dart';
import '../features/parent/child_dashboard_screen.dart';
import '../features/parent/child_form_screen.dart';
import '../features/parent/child_settings_screen.dart';
import '../features/homework/homework_screen.dart';
import '../features/homework/homework_start_screen.dart';
import '../features/teach/teach_screen.dart';
import '../features/parent/child_help_screen.dart';
import '../features/parent/child_homework_screen.dart';
import '../features/parent/child_teach_screen.dart';
import '../features/parent/child_programme_screen.dart';
import '../features/parent/child_reports_screen.dart';
import '../features/parent/child_mistakes_screen.dart';
import '../features/parent/child_skills_screen.dart';
import '../features/parent/lesson_content_screen.dart';
import '../features/parent/email_verification_screen.dart';
import '../features/parent/goals_screen.dart';
import '../features/parent/link_code_screen.dart';
import '../features/parent/parent_home_screen.dart';
import '../features/parent/parent_sign_in_screen.dart';
import '../features/parent/password_reset_screen.dart';
import '../features/rewards/badges_screen.dart';
import '../features/session/session_screen.dart';
import '../features/start/splash_screen.dart';
import '../features/start/start_screen.dart';

abstract final class Routes {
  static const splash = '/chargement';
  static const start = '/';
  static const parentSignIn = '/parent/connexion';
  static const parentRegister = '/parent/inscription';
  static const parentHome = '/parent';
  static const forgotPassword = '/parent/mot-de-passe-oublie';

  /// Ouvert par le lien de l'e-mail : `ludifun://app/parent/nouveau-mot-de-passe?jeton=…`.
  static const newPassword = '/parent/nouveau-mot-de-passe';

  /// Ouvert par le lien « Confirmez votre adresse » : `ludifun://app/parent/verifier-email?jeton=…`.
  static const verifyEmail = '/parent/verifier-email';
  static const addChild = '/parent/enfants/nouveau';
  static const aiSettings = '/parent/ia';
  static String childDashboard(String childId) => '/parent/enfants/$childId';
  static String childLink(String childId) => '/parent/enfants/$childId/lier';
  static String childSettings(String childId) => '/parent/enfants/$childId/reglages';
  static String childSkills(String childId) => '/parent/enfants/$childId/competences';
  static String childProgramme(String childId) => '/parent/enfants/$childId/programme';
  static String childGoals(String childId) => '/parent/enfants/$childId/objectifs';
  static String childMistakes(String childId) => '/parent/enfants/$childId/erreurs';
  static String childHelp(String childId) => '/parent/enfants/$childId/aides';
  static String childReports(String childId) => '/parent/enfants/$childId/signalements';
  static String lessonContent(String childId, String lessonId) =>
      '/parent/enfants/$childId/lecons/$lessonId';
  static String childEdit(String childId) => '/parent/enfants/$childId/modifier';
  static String childCapture(String childId) => '/parent/enfants/$childId/photo';
  static String childPaste(String childId) => '/parent/enfants/$childId/texte';
  static const link = '/lier';
  static const scanQr = '/lier/qr';
  static const childHome = '/enfant';
  static const capture = '/enfant/photo';
  static const paste = '/enfant/texte';
  static const badges = '/enfant/badges';
  static const homeworkStart = '/enfant/devoirs';
  static String homework(String id) => '/enfant/devoirs/$id';
  static String childHomework(String childId) => '/parent/enfants/$childId/devoirs';
  static String teach(String id) => '/enfant/enseigne/$id';
  static String childTeach(String childId) => '/parent/enfants/$childId/enseigne';
  static String analysis(String lessonId, {String? childId}) =>
      childId == null ? '/enfant/analyse/$lessonId' : '/parent/enfants/$childId/analyse/$lessonId';
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
    Routes.forgotPassword,
  };
  // Liens des e-mails, quel que soit l'espace ouvert sur le téléphone.
  if (location == Routes.newPassword || location == Routes.verifyEmail) return null;
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
      GoRoute(path: Routes.forgotPassword, builder: (_, _) => const PasswordResetScreen()),
      GoRoute(
        path: Routes.newPassword,
        builder: (_, state) => PasswordResetScreen(token: state.uri.queryParameters['jeton'] ?? ''),
      ),
      GoRoute(
        path: Routes.verifyEmail,
        builder: (_, state) =>
            EmailVerificationScreen(token: state.uri.queryParameters['jeton'] ?? ''),
      ),
      GoRoute(
        path: Routes.parentHome,
        builder: (_, _) => const ParentHomeScreen(),
        routes: [
          GoRoute(path: 'enfants/nouveau', builder: (_, _) => const ChildFormScreen()),
          GoRoute(path: 'ia', builder: (_, _) => const AiSettingsScreen()),
          GoRoute(
            path: 'enfants/:id',
            builder: (_, state) => ChildDashboardScreen(childId: state.pathParameters['id']!),
            routes: [
              GoRoute(
                path: 'lier',
                builder: (_, state) => LinkCodeScreen(childId: state.pathParameters['id']!),
              ),
              GoRoute(
                path: 'reglages',
                builder: (_, state) => ChildSettingsScreen(childId: state.pathParameters['id']!),
              ),
              GoRoute(
                path: 'objectifs',
                builder: (_, state) => GoalsScreen(childId: state.pathParameters['id']!),
              ),
              GoRoute(
                path: 'lecons/:lesson',
                builder: (_, state) => LessonContentScreen(
                  childId: state.pathParameters['id']!,
                  lessonId: state.pathParameters['lesson']!,
                ),
              ),
              GoRoute(
                path: 'erreurs',
                builder: (_, state) => ChildMistakesScreen(childId: state.pathParameters['id']!),
              ),
              GoRoute(
                path: 'aides',
                builder: (_, state) => ChildHelpScreen(childId: state.pathParameters['id']!),
              ),
              GoRoute(
                path: 'signalements',
                builder: (_, state) => ChildReportsScreen(childId: state.pathParameters['id']!),
              ),
              GoRoute(
                path: 'competences',
                builder: (_, state) => ChildSkillsScreen(childId: state.pathParameters['id']!),
              ),
              GoRoute(
                path: 'programme',
                builder: (_, state) => ChildProgrammeScreen(childId: state.pathParameters['id']!),
              ),
              GoRoute(
                path: 'devoirs',
                builder: (_, state) => ChildHomeworkScreen(childId: state.pathParameters['id']!),
              ),
              GoRoute(
                path: 'enseigne',
                builder: (_, state) => ChildTeachScreen(childId: state.pathParameters['id']!),
              ),
              GoRoute(
                path: 'modifier',
                builder: (_, state) => ChildFormScreen(childId: state.pathParameters['id']),
              ),
              GoRoute(
                path: 'photo',
                builder: (_, state) => CaptureScreen(childId: state.pathParameters['id']),
              ),
              GoRoute(
                path: 'texte',
                builder: (_, state) => TextImportScreen(childId: state.pathParameters['id']),
              ),
              GoRoute(
                path: 'analyse/:lesson',
                builder: (_, state) => AnalysisScreen(
                  lessonId: state.pathParameters['lesson']!,
                  childId: state.pathParameters['id'],
                ),
              ),
            ],
          ),
        ],
      ),
      GoRoute(path: Routes.link, builder: (_, _) => const LinkScreen()),
      GoRoute(path: Routes.scanQr, builder: (_, _) => const QrScanScreen()),
      GoRoute(
        path: Routes.childHome,
        builder: (_, _) => const ChildHomeScreen(),
        routes: [
          GoRoute(path: 'photo', builder: (_, _) => const CaptureScreen()),
          GoRoute(path: 'texte', builder: (_, _) => const TextImportScreen()),
          GoRoute(path: 'badges', builder: (_, _) => const BadgesScreen()),
          GoRoute(path: 'devoirs', builder: (_, _) => const HomeworkStartScreen()),
          GoRoute(
            path: 'devoirs/:id',
            builder: (_, state) => HomeworkScreen(homeworkId: state.pathParameters['id']!),
          ),
          GoRoute(
            path: 'enseigne/:id',
            builder: (_, state) => TeachScreen(teachId: state.pathParameters['id']!),
          ),
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
