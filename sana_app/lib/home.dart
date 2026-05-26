import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter_phone_direct_caller/flutter_phone_direct_caller.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:image_picker/image_picker.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

import 'contact.dart';
import 'setting.dart';

const String _piBaseUrl = 'http://192.168.8.118:5050';
const Duration _pollInterval = Duration(seconds: 1);

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  static bool _hasSpokenWelcome = false;

  final FlutterTts _flutterTts = FlutterTts();
  final ImagePicker _picker = ImagePicker();
  final stt.SpeechToText _speech = stt.SpeechToText();

  String? selectedCard;

  Timer? _pollTimer;
  String _currentLocation = '—';
  bool _bridgeConnected = false;
  bool _speechReady = false;
  bool _isListeningCommand = false;

  static const String ocrApiUrl =
      'https://roundup-sleet-autopilot.ngrok-free.dev/ocr';

  static const String reportApiUrl =
      'https://ouch-suspect-emission.ngrok-free.dev/report-obstacle';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Future.delayed(const Duration(milliseconds: 800));
      if (!mounted) return;

      await _speak(' الرئيسية');

if (!_hasSpokenWelcome) {
  _hasSpokenWelcome = true;
  await Future.delayed(const Duration(seconds: 2));
  if (!mounted) return;
  await _speakWelcome();
}
    });
    _startBridgePolling();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _speech.stop();
    _flutterTts.stop();
    super.dispose();
  }

  Future<void> _speak(String text) async {
    await _flutterTts.setLanguage('ar-SA');
    await _flutterTts.setSpeechRate(0.45);
    await _flutterTts.setPitch(1.0);
    await _flutterTts.speak(text);
  }

  Future<void> _speakWelcome() => _speak('مرحبا أنا سَنَا');

  void _showSnackAndSpeak(String message) {
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );

    _speak(message);
  }
Future<void> _showPopupAndSpeak({
  required String title,
  required String message,
  IconData icon = Icons.info_outline,
}) async {
  if (!mounted) return;

  await _speak(message);

  if (!mounted) return;

  showDialog(
    context: context,
    builder: (dialogContext) {
      return Directionality(
        textDirection: TextDirection.rtl,
        child: Dialog(
          backgroundColor: Colors.transparent,
          child: Container(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 18),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(22),
              border: Border.all(color: const Color(0xFFD9D9D9)),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  icon,
                  color: const Color(0xFF640000),
                  size: 54,
                ),
                const SizedBox(height: 14),
                Text(
                  title,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 30,
                    fontWeight: FontWeight.w900,
                    color: Colors.black,
                  ),
                ),
                const SizedBox(height: 14),
                Text(
                  message,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.w700,
                    color: Colors.black,
                    height: 1.35,
                  ),
                ),
                const SizedBox(height: 22),
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: () => Navigator.pop(dialogContext),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF640000),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                      elevation: 0,
                    ),
                    child: const Text(
                      'حسناً',
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w900,
                        color: Colors.white,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    },
  );
}
  Future<void> _listenForHomeCommand() async {
    if (_isListeningCommand) return;

    if (!_speechReady) {
      _speechReady = await _speech.initialize();
    }

    if (!_speechReady) {
      _showSnackAndSpeak('تعذر تشغيل الميكروفون');
      return;
    }

    setState(() => _isListeningCommand = true);

    await _speak('قولي الأمر');
    await Future.delayed(const Duration(milliseconds: 1200));

    String command = '';

    await _speech.listen(
      localeId: 'ar_SA',
      listenFor: const Duration(seconds: 8),
      pauseFor: const Duration(seconds: 3),
      onResult: (result) {
        command = result.recognizedWords;
      },
    );

    await Future.delayed(const Duration(seconds: 8));
    await _speech.stop();

    if (!mounted) return;

    setState(() => _isListeningCommand = false);

    command = command.trim();

    if (command.isEmpty) {
      _showSnackAndSpeak('لم أسمع الأمر');
      return;
    }

    await _handleHomeVoiceCommand(command);
  }

  Future<void> _handleHomeVoiceCommand(String command) async {
    final text = command
        .replaceAll('سنا', '')
        .replaceAll('سانا', '')
        .replaceAll('أنا أريد', '')
        .replaceAll('اريد', '')
        .replaceAll('أريد', '')
        .replaceAll('ابي', '')
        .replaceAll('أبي', '')
        .trim();

    if (text.contains('قراءة') ||
        text.contains('اقرأ') ||
        text.contains('نص') ||
        text.contains('النص')) {
      setState(() => selectedCard = 'readText');
      await _speak('فتح قراءة النص');
      if (mounted) await _readPrintedText(context);
      return;
    }

    if (text.contains('موقعي') ||
        text.contains('موقع') ||
        text.contains('الحالي') ||
        text.contains('اين انا') ||
        text.contains('وين انا')) {
      setState(() => selectedCard = 'exactLocation');
      await _speak('طلب الموقع الحالي');
      if (mounted) await _requestLocationFromPi(context);
      return;
    }

    if (text.contains('وجهة') ||
    text.contains('وجهةٌ') ||
    text.contains('جديدة') ||
    text.contains('جديدةٌ') ||
    text.contains('جديده') ||
    text.contains('وجهه') ||
        text.contains('اذهب') ||
        text.contains('تنقل') ||
        text.contains('مكان')) {
      setState(() => selectedCard = 'destination');
      await _speak('طلب وجهة جديدة');
      if (mounted) await _requestNewDestination(context);
      return;
    }

    if (text.contains('عائق') ||
        text.contains('بلاغ') ||
        text.contains('ابلاغ') ||
        text.contains('إبلاغ')) {
      setState(() => selectedCard = 'reportObstacle');
      await _speak('فتح بلاغ عن عائق');
      if (mounted) await _reportObstacleWithApi(context);
      return;
    }

    if (text.contains('طوارئ') ||
        text.contains('اتصال') ||
        text.contains('اتصلي')) {
      setState(() => selectedCard = 'emergency');
      await _speak('جارٍ الاتصال بجهة الطوارئ');
      if (mounted) await _callPrimaryContact(context);
      return;
    }

    _showSnackAndSpeak('لم أفهم الأمر');
  }

  void _startBridgePolling() {
    _pollTimer = Timer.periodic(_pollInterval, (_) => _pollBridgeEvents());
  }

  Future<void> _pollBridgeEvents() async {
    try {
      final response = await http
          .get(Uri.parse('$_piBaseUrl/events'))
          .timeout(const Duration(seconds: 2));

      if (!mounted) return;

      if (response.statusCode == 200) {
        setState(() => _bridgeConnected = true);

        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final events = (data['events'] as List?) ?? [];

        for (final ev in events) {
          await _handleBridgeEvent(ev as Map<String, dynamic>);
        }
      }
    } catch (_) {
      if (mounted) setState(() => _bridgeConnected = false);
    }
  }

  Future<void> _handleBridgeEvent(Map<String, dynamic> ev) async {
    final type = ev['type'] as String? ?? '';

    switch (type) {
      case 'emergency':
        await _speak('جارٍ الاتصال بجهة الطوارئ');
        if (mounted) await _callPrimaryContact(context);
        break;

      case 'location_response':
        final place = ev['place'] as String? ?? '';
        final node = ev['node'] as String? ?? '';
        final heading = ev['heading_ar'] as String? ?? '';
        final display = place.isNotEmpty ? place : 'عقدة $node';
        final fullMsg = heading.isNotEmpty ? '$display، اتجاه $heading' : display;

        setState(() => _currentLocation = fullMsg);
        await _speak(fullMsg);

        if (mounted) _showLocationDialog(display);
        break;

      case 'stop_navigation':
        await _speak('توقف التنقل');
        break;
    }
  }

  Future<void> _requestLocationFromPi(BuildContext context) async {
    try {
      final response = await http
          .post(
            Uri.parse('$_piBaseUrl/command'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'cmd': 'get_location'}),
          )
          .timeout(const Duration(seconds: 3));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final location = (data['place'] ??
                data['location'] ??
                data['current_location'] ??
                data['node'])
            ?.toString()
            .trim();

        if (location == null || location.isEmpty) return;

        setState(() => _currentLocation = location);
      } else {
        _showSnackAndSpeak('النظارات غير متصلة');
      }
    } catch (_) {
      _showSnackAndSpeak('النظارات غير متصلة بالشبكة');
    }
  }

  Future<void> _requestNewDestination(BuildContext context) async {
    try {
      final response = await http
          .post(
            Uri.parse('$_piBaseUrl/command'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'cmd': 'new_destination'}),
          )
          .timeout(const Duration(seconds: 3));

      if (response.statusCode != 200) {
        _showSnackAndSpeak('النظارات غير متصلة');
      }
    } catch (_) {
      _showSnackAndSpeak('النظارات غير متصلة بالشبكة');
    }
  }

  void _showLocationDialog(String locationText) {
    const burgundy = Color(0xFF640000);

    showDialog(
      context: context,
      barrierColor: Colors.white,
      builder: (dialogContext) {
        return Directionality(
          textDirection: TextDirection.rtl,
          child: Dialog.fullscreen(
            backgroundColor: Colors.white,
            child: SafeArea(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 22),
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.fromLTRB(18, 30, 18, 24),
                  decoration: BoxDecoration(
                    color: Colors.black,
                    borderRadius: BorderRadius.circular(30),
                  ),
                  child: Column(
                    children: [
                      Align(
                        alignment: Alignment.centerRight,
                        child: TextButton.icon(
                          onPressed: () => Navigator.pop(dialogContext),
                          style: TextButton.styleFrom(
                            backgroundColor: Colors.white,
                            foregroundColor: Colors.black,
                            padding: const EdgeInsets.symmetric(
                              horizontal: 22,
                              vertical: 10,
                            ),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14),
                            ),
                          ),
                          icon: const Icon(Icons.arrow_back, size: 42),
                          label: const Text(
                            'رجوع',
                            style: TextStyle(
                              fontSize: 36,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 54),
                      const Text(
                        'موقعي الحالي',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 48,
                          fontWeight: FontWeight.w900,
                          height: 1,
                        ),
                      ),
                      const SizedBox(height: 36),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.fromLTRB(18, 34, 18, 30),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(18),
                        ),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              Icons.location_on_outlined,
                              color: burgundy,
                              size: 96,
                            ),
                            const SizedBox(height: 24),
                            const Text(
                              'موقعك الحالي:',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: Colors.black,
                                fontSize: 40,
                                fontWeight: FontWeight.w900,
                                height: 1.1,
                              ),
                            ),
                            const SizedBox(height: 22),
                            Text(
                              locationText,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                color: burgundy,
                                fontSize: 34,
                                fontWeight: FontWeight.w900,
                                height: 1.25,
                              ),
                            ),
                            const SizedBox(height: 26),
                            GestureDetector(
                              onTap: () => Navigator.pop(dialogContext),
                              child: Container(
                                width: double.infinity,
                                padding: const EdgeInsets.symmetric(vertical: 12),
                                decoration: BoxDecoration(
                                  color: burgundy,
                                  borderRadius: BorderRadius.circular(10),
                                ),
                                child: const Text(
                                  'العودة للرئيسية',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 32,
                                    fontWeight: FontWeight.w900,
                                    height: 1,
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Future<void> _readPrintedText(BuildContext context) async {
  try {
    final image = await _picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 85,
    );

    if (image == null) return;

    final arabicText = await _sendImageToOcrApi(File(image.path));

    if (arabicText.trim().isEmpty) {
      await _showPopupAndSpeak(
        title: 'قراءة النص',
        message: 'لم يتم العثور على نص',
        icon: Icons.document_scanner_outlined,
      );
      return;
    }

    await _showPopupAndSpeak(
      title: 'النص المقروء',
      message: arabicText,
      icon: Icons.article_outlined,
    );
  } catch (e) {
    await _showPopupAndSpeak(
      title: 'خطأ',
      message: 'حدث خطأ أثناء قراءة النص',
      icon: Icons.error_outline,
    );
  }
}

  Future<String> _sendImageToOcrApi(File imageFile) async {
    final request = http.MultipartRequest('POST', Uri.parse(ocrApiUrl));

    request.files.add(
      await http.MultipartFile.fromPath(
        'file',
        imageFile.path,
        contentType: MediaType('image', 'jpeg'),
      ),
    );

    final response = await request.send();
    final responseBody = await response.stream.bytesToString();

    if (response.statusCode != 200) throw Exception(responseBody);

    final data = jsonDecode(responseBody) as Map<String, dynamic>;

    if (data['success'] != true) throw Exception('OCR failed');

    return data['arabic_text']?.toString() ?? '';
  }

  Future<void> _callPrimaryContact(BuildContext context) async {
  final user = FirebaseAuth.instance.currentUser;

  if (user == null) {
    await _showPopupAndSpeak(
      title: 'تنبيه',
      message: 'لا يوجد مستخدم مسجل حالياً',
      icon: Icons.person_off_outlined,
    );
    return;
  }

  try {
    final contactsSnapshot = await FirebaseFirestore.instance
        .collection('Contact')
        .where('userId', isEqualTo: user.uid)
        .limit(1)
        .get();

    if (contactsSnapshot.docs.isEmpty) {
      await _showPopupAndSpeak(
        title: 'لا توجد جهة اتصال',
        message: 'لا توجد جهة اتصال محفوظة',
        icon: Icons.contact_phone_outlined,
      );
      return;
    }

    final primarySnapshot = await FirebaseFirestore.instance
        .collection('Contact')
        .where('userId', isEqualTo: user.uid)
        .where('isPrimary', isEqualTo: true)
        .limit(1)
        .get();

    if (primarySnapshot.docs.isEmpty) {
      await _showPopupAndSpeak(
        title: 'لا توجد جهة طوارئ',
        message: 'لا توجد جهة اتصال أساسية',
        icon: Icons.contact_phone_outlined,
      );
      return;
    }

    final phoneNumber =
        (primarySnapshot.docs.first.data()['phoneNumber'] as String? ?? '')
            .trim();

    if (phoneNumber.isEmpty) {
      await _showPopupAndSpeak(
        title: 'خطأ',
        message: 'رقم الهاتف غير موجود',
        icon: Icons.phone_disabled_outlined,
      );
      return;
    }

    await _showPopupAndSpeak(
      title: 'اتصال طارئ',
      message: 'جارٍ الاتصال بجهة الطوارئ',
      icon: Icons.call_outlined,
    );

    await FlutterPhoneDirectCaller.callNumber(phoneNumber);
  } catch (e) {
    await _showPopupAndSpeak(
      title: 'خطأ',
      message: 'حدث خطأ أثناء الاتصال',
      icon: Icons.error_outline,
    );
  }
}

  Future<void> _reportObstacleWithApi(BuildContext context) async {
  try {
    final image = await _picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 70,
    );

    if (image == null) return;

    final request = http.MultipartRequest(
      'POST',
      Uri.parse(reportApiUrl),
    );

    request.files.add(
      await http.MultipartFile.fromPath(
        'image',
        image.path,
        contentType: MediaType('image', 'jpeg'),
      ),
    );

    final response = await request.send();

    if (response.statusCode == 200) {
      await _showPopupAndSpeak(
        title: 'تم إرسال البلاغ',
        message: 'تم إرسال البلاغ بنجاح',
        icon: Icons.check_circle_outline,
      );
    } else {
      await _showPopupAndSpeak(
        title: 'تعذر الإرسال',
        message: 'تعذر إرسال البلاغ. حاولي مرة أخرى',
        icon: Icons.error_outline,
      );
    }
  } catch (_) {
    await _showPopupAndSpeak(
      title: 'تعذر الإرسال',
      message: 'تعذر إرسال البلاغ. تحققي من الاتصال وحاولي مرة أخرى',
      icon: Icons.wifi_off_outlined,
    );
  }
}
  @override
  Widget build(BuildContext context) {
    const burgundy = Color(0xFF640000);

    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
  backgroundColor: Colors.white,
 floatingActionButtonLocation: FloatingActionButtonLocation.startFloat,
floatingActionButton: Padding(
  padding: const EdgeInsets.only(bottom: 72),
  child: InkWell(
    borderRadius: BorderRadius.circular(999),
    onTap: _listenForHomeCommand,
    child: Container(
      width: 72,
      height: 72,
      decoration: BoxDecoration(
        color: Colors.white,
        shape: BoxShape.circle,
        border: Border.all(
          color: Color(0xFF640000),
          width: 2,
        ),
        boxShadow: const [
          BoxShadow(
            color: Color(0x26000000),
            blurRadius: 8,
            offset: Offset(0, 3),
          ),
        ],
      ),
      child: const Icon(
        Icons.mic_none_outlined,
        color: Color(0xFF640000),
        size: 40,
      ),
    ),
  ),
),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
            child: Column(
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          _bridgeConnected ? Icons.circle : Icons.circle_outlined,
                          size: 9,
                          color: _bridgeConnected
                              ? const Color(0xFF00C48C)
                              : Colors.grey,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          _bridgeConnected
                              ? 'النظارات متصلة'
                              : 'النظارات غير متصلة',
                          style: TextStyle(
                            fontSize: 11,
                            color: _bridgeConnected
                                ? const Color(0xFF00C48C)
                                : Colors.grey,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 4),
                Expanded(
                  child: ListView(
                    padding: const EdgeInsets.only(top: 2, bottom: 76),
                    children: [
                      
                      HomeActionCard(
                        title: 'وجهة جديدة',
                        icon: Icons.map_outlined,
                        color: burgundy,
                        selected: selectedCard == 'destination',
                        onTap: () {
                          setState(() => selectedCard = 'destination');
                          _requestNewDestination(context);
                        },
                      ),
                      const SizedBox(height: 1),
                      HomeActionCard(
                        title: 'قراءة نص',
                        icon: Icons.document_scanner_outlined,
                        color: burgundy,
                        selected: selectedCard == 'readText',
                        onTap: () {
                          setState(() => selectedCard = 'readText');
                          _readPrintedText(context);
                        },
                      ),
                      const SizedBox(height: 1),
                      HomeActionCard(
                        title: 'موقعي الحالي',
                        icon: Icons.my_location_outlined,
                        color: burgundy,
                        selected: selectedCard == 'exactLocation',
                        onTap: () {
                          setState(() => selectedCard = 'exactLocation');
                          _requestLocationFromPi(context);
                        },
                      ),
                      const SizedBox(height: 1),
                      HomeActionCard(
                        title: 'إبلاغ عن عائق',
                        icon: Icons.warning_amber_rounded,
                        color: burgundy,
                        selected: selectedCard == 'reportObstacle',
                        onTap: () {
                          setState(() => selectedCard = 'reportObstacle');
                          _reportObstacleWithApi(context);
                        },
                      ),
                      const SizedBox(height: 1),
                      EmergencyActionCard(
                        color: burgundy,
                        selected: selectedCard == 'emergency',
                        onLongPress: () {
                          setState(() => selectedCard = 'emergency');
                          _callPrimaryContact(context);
                        },
                      ),
                    ],
                  ),
                ),
                Container(
                  height: 72,
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(color: const Color(0xFFD9D9D9)),
                  ),
                  child: Row(
                    children: [
                      const Expanded(
                        child: NavItem(
                          icon: Icons.home_outlined,
                          selected: true,
                        ),
                      ),
                      Expanded(
                        child: NavItem(
                          icon: Icons.settings_outlined,
                          selected: false,
                          onTap: () => Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => const SettingPage(),
                            ),
                          ),
                        ),
                      ),
                      Expanded(
                        child: NavItem(
                          icon: Icons.call_outlined,
                          selected: false,
                          onTap: () => Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => const ContactPage(),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class HomeActionCard extends StatelessWidget {
  final String title;
  final IconData icon;
  final Color color;
  final VoidCallback onTap;
  final bool selected;

  const HomeActionCard({
    super.key,
    required this.title,
    required this.icon,
    required this.color,
    required this.onTap,
    required this.selected,
  });

  @override
  Widget build(BuildContext context) {
    return _OutlinedCardShell(
      selected: selected,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(26),
        child: Container(
          height: 100,
          padding: const EdgeInsets.symmetric(horizontal: 18),
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(26),
          ),
          child: Row(
            children: [
              Container(
                width: 58,
                height: 58,
                decoration: const BoxDecoration(
                  color: Colors.white,
                  shape: BoxShape.circle,
                ),
                child: Icon(icon, color: color, size: 32),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.centerRight,
                  child: Text(
                    title,
                    textAlign: TextAlign.right,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 45,
                      fontWeight: FontWeight.w900,
                      height: 1,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class EmergencyActionCard extends StatelessWidget {
  final Color color;
  final VoidCallback onLongPress;
  final bool selected;

  const EmergencyActionCard({
    super.key,
    required this.color,
    required this.onLongPress,
    required this.selected,
  });

  @override
  Widget build(BuildContext context) {
    return _OutlinedCardShell(
      selected: selected,
      child: InkWell(
        onLongPress: onLongPress,
        borderRadius: BorderRadius.circular(26),
        child: Container(
          height: 100,
          padding: const EdgeInsets.symmetric(horizontal: 32),
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(26),
          ),
          child: Row(
            children: [
              Container(
                width: 58,
                height: 58,
                decoration: const BoxDecoration(
                  color: Colors.white,
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.add_alert_rounded, color: color, size: 32),
              ),
              const SizedBox(width: 8),
              const Expanded(
                child: SizedBox(
                  width: double.infinity,
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      FittedBox(
                        fit: BoxFit.scaleDown,
                        alignment: Alignment.centerRight,
                        child: Text(
                          'اتصال طارئ',
                          textAlign: TextAlign.right,
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 45,
                            fontWeight: FontWeight.w900,
                            height: 1,
                          ),
                        ),
                      ),
                      SizedBox(height: 2),
                      Text(
                        'اضغط مطولاً لتفعيل الاتصال الطارئ',
                        textAlign: TextAlign.right,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          height: 1,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _OutlinedCardShell extends StatelessWidget {
  final Widget child;
  final bool selected;

  const _OutlinedCardShell({
    required this.child,
    required this.selected,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(
        color: selected ? Colors.black : Colors.transparent,
        borderRadius: BorderRadius.circular(30),
        boxShadow: selected
            ? const [
                BoxShadow(
                  color: Color(0x26000000),
                  blurRadius: 10,
                  offset: Offset(0, 4),
                )
              ]
            : null,
      ),
      child: Container(
        padding: const EdgeInsets.all(1),
        decoration: BoxDecoration(
          color: selected ? Colors.white : Colors.transparent,
          borderRadius: BorderRadius.circular(28),
        ),
        child: child,
      ),
    );
  }
}

class NavItem extends StatelessWidget {
  final IconData icon;
  final bool selected;
  final VoidCallback? onTap;

  const NavItem({
    super.key,
    required this.icon,
    required this.selected,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        alignment: Alignment.center,
        child: Icon(
          icon,
          size: 50,
          color: selected ? const Color(0xFF640000) : Colors.grey,
        ),
      ),
    );
  }
}
