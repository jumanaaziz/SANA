import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:volume_controller/volume_controller.dart';
import 'contact.dart';
import 'home.dart';
import 'welcome.dart';

class SettingPage extends StatefulWidget {
  final bool openDeleteDialog;

  const SettingPage({
    super.key,
    this.openDeleteDialog = false,
  });

  @override
  State<SettingPage> createState() => _SettingPageState();
}

class _SettingPageState extends State<SettingPage> {
  double volume = 0.7;
  bool _isDeleting = false;
  bool _speechReady = false;
  bool _isListeningCommand = false;
  final FlutterTts _flutterTts = FlutterTts();
  final stt.SpeechToText _speech = stt.SpeechToText();



  @override
  void initState() {
    super.initState();
    _loadVolume();
    VolumeController.instance.showSystemUI = false;

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      await _speak(' الإعدادات');

      if (mounted && widget.openDeleteDialog) {
        _showDeleteDialog();
      }
    });
  }

  @override
  void dispose() {
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

  Future<void> _speakDeleteAccountMessage() async {
    await _speak('هل أنتِ متأكدةٌ من رغبتكِ في حذف الحساب نهائيًا؟');
  }

  Future<String?> _listenArabicCommand() async {
    if (!_speechReady) {
      _speechReady = await _speech.initialize();
    }

    if (!_speechReady) {
      await _speak('تعذر تشغيل الميكروفون');
      return null;
    }

    String result = '';

    await _speech.stop();

    await _speech.listen(
      localeId: 'ar_SA',
      listenFor: const Duration(seconds: 10),
      pauseFor: const Duration(seconds: 3),
      partialResults: true,
      onResult: (value) {
        result = value.recognizedWords;
      },
    );

    await Future.delayed(const Duration(seconds: 10));
    await _speech.stop();

    return result.trim().isEmpty ? null : result.trim();
  }

  Future<void> _listenForSettingCommand() async {
    if (_isListeningCommand) return;

    setState(() => _isListeningCommand = true);

    await _speak('قولي الأمر');
    final command = await _listenArabicCommand();

    if (!mounted) return;
    setState(() => _isListeningCommand = false);

    final text = command
            ?.replaceAll('سنا', '')
            .replaceAll('سانا', '')
            .replaceAll('أريد', '')
            .replaceAll('اريد', '')
            .replaceAll('ابي', '')
            .replaceAll('أبي', '')
            .trim() ??
        '';

    if ((text.contains('حذف') || text.contains('احذف')) &&
        (text.contains('حساب') || text.contains('الحساب'))) {
      _showDeleteDialog();
      return;
    }

    await _speak(text.isEmpty ? 'لم أسمع الأمر' : 'لم أفهم الأمر');
  }

  Future<void> _loadVolume() async {
    final currentVolume = await VolumeController.instance.getVolume();
    if (!mounted) return;
    setState(() {
      volume = currentVolume;
    });
  }

  Future<void> _updateVolume(double value) async {
    setState(() {
      volume = value;
    });
    await VolumeController.instance.setVolume(value);
  }

  Future<void> _deleteAccount() async {
    final user = FirebaseAuth.instance.currentUser;

    if (user == null) {
      if (!mounted) return;
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (_) => const WelcomePage()),
        (route) => false,
      );
      return;
    }

    setState(() {
      _isDeleting = true;
    });

    try {
      final uid = user.uid;

      await FirebaseFirestore.instance.collection('User').doc(uid).delete();
      await user.delete();

      if (!mounted) return;
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (_) => const WelcomePage()),
        (route) => false,
      );
    } on FirebaseAuthException catch (e) {
      String message = 'تعذر حذف الحساب';

      if (e.code == 'requires-recent-login') {
        message = 'لحذف الحساب يجب تسجيل الدخول مرة أخرى أولاً';
      }

      if (!mounted) return;
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
    } catch (e) {
      if (!mounted) return;
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('حدث خطأ: $e')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isDeleting = false;
        });
      }
    }
  }

  void _showDeleteDialog() {
    const burgundy = Color(0xFF640000);
_speakDeleteAccountMessage();
    showDialog(
      context: context,
      barrierDismissible: !_isDeleting,
      builder: (dialogContext) {
        return Dialog(
          backgroundColor: Colors.transparent,
          child: Container(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 18),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(24),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.delete_outline,
                  color: burgundy,
                  size: 42,
                ),
                const SizedBox(height: 14),
                const Text(
                  'هل أنتِ متأكدة من\nرغبتك في حذف\nالحساب نهائيًا؟',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w900,
                    color: Colors.black,
                    height: 1.2,
                  ),
                ),
                const SizedBox(height: 22),
                SizedBox(
                  width: double.infinity,
                  height: 62,
                  child: ElevatedButton(
                    onPressed: _isDeleting ? null : _deleteAccount,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: burgundy,
                      disabledBackgroundColor: burgundy,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                      elevation: 0,
                    ),
                    child: _isDeleting
                        ? const CircularProgressIndicator(color: Colors.white)
                        : const Text(
                            'تأكيد',
                            style: TextStyle(
                              fontSize: 26,
                              fontWeight: FontWeight.w900,
                              color: Colors.white,
                            ),
                          ),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  height: 62,
                  child: ElevatedButton(
                    onPressed: _isDeleting
                        ? null
                        : () => Navigator.pop(dialogContext),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFFE7EAEE),
                      disabledBackgroundColor: const Color(0xFFE7EAEE),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                      elevation: 0,
                    ),
                    child: const Text(
                      'إلغاء',
                      style: TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w900,
                        color: Colors.black,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
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
    onTap: _listenForSettingCommand,
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
                const SizedBox(height: 8),
                const Text(
                  'الإعدادات',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 50,
                    fontWeight: FontWeight.w900,
                    color: Colors.black,
                  ),
                ),
                const SizedBox(height: 28),
                Container(
                  width: double.infinity,
                  height: 70,
                  decoration: BoxDecoration(
                    color: burgundy,
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: const Center(
                    child: Text(
                      'التنبيهات السمعية',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 45,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 18,
                  ),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF9F9F9),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: const Color(0xFFD9D9D9)),
                  ),
                  child: Column(
                    children: [
                      const Row(
                        children: [
                          Icon(
                            Icons.volume_up_outlined,
                            color: burgundy,
                            size: 34,
                          ),
                          SizedBox(width: 8),
                          Text(
                            'مستوى الصوت',
                            style: TextStyle(
                              fontSize: 48,
                              fontWeight: FontWeight.w900,
                              color: Colors.black,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 18),
                      SizedBox(
                        height: 52,
                        child: Stack(
                          alignment: Alignment.center,
                          children: [
                            Container(
                              height: 52,
                              decoration: BoxDecoration(
                                color: const Color(0xFFE3E7EC),
                                borderRadius: BorderRadius.circular(8),
                              ),
                            ),
                            Align(
                              alignment: Alignment.centerRight,
                              child: FractionallySizedBox(
                                widthFactor: volume.clamp(0.0, 1.0),
                                child: Container(
                                  height: 52,
                                  decoration: BoxDecoration(
                                    color: burgundy,
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                ),
                              ),
                            ),
                            SliderTheme(
                              data: SliderTheme.of(context).copyWith(
                                trackHeight: 52,
                                activeTrackColor: Colors.transparent,
                                inactiveTrackColor: Colors.transparent,
                                thumbColor: Colors.transparent,
                                overlayColor: Colors.transparent,
                                thumbShape: const RoundSliderThumbShape(
                                  enabledThumbRadius: 0,
                                ),
                                overlayShape: SliderComponentShape.noOverlay,
                              ),
                              child: Slider(
                                value: volume,
                                min: 0.0,
                                max: 1.0,
                                onChanged: _updateVolume,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 18),
                      const Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'منخفض',
                            style: TextStyle(
                              fontSize: 40,
                              fontWeight: FontWeight.w900,
                              color: Colors.black,
                            ),
                          ),
                          Text(
                            'مرتفع',
                            style: TextStyle(
                              fontSize: 40,
                              fontWeight: FontWeight.w900,
                              color: Colors.black,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                                const Spacer(),
                Transform.translate(
                  offset: const Offset(0, -60),
                  child: SizedBox(
                    width: double.infinity,
                    height: 70,
                    child: ElevatedButton(
                      onPressed: _showDeleteDialog,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: burgundy,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16),
                        ),
                        elevation: 0,
                      ),
                      child: const Text(
                        'حذف الحساب',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 45,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                Container(
                  height: 72,
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(color: const Color(0xFFD9D9D9)),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: NavItem(
                          icon: Icons.home_outlined,
                          selected: false,
                          onTap: () {
                           Navigator.push(
  context,
  MaterialPageRoute(
    builder: (_) => const HomePage(),
  ),
);
                          },
                        ),
                      ),
                      const Expanded(
                        child: NavItem(
                          icon: Icons.settings_outlined,
                          selected: true,
                        ),
                      ),
                      Expanded(
                        child: NavItem(
                          icon: Icons.call_outlined,
                          selected: false,
                          onTap: () {
                            Navigator.pushReplacement(
                              context,
                              MaterialPageRoute(
                                builder: (_) => const ContactPage(),
                              ),
                            );
                          },
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
