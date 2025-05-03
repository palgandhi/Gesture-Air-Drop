import cv2
import mediapipe as mp
import threading
import time

class HandDetector:
    def __init__(self, mode=False, max_hands=2, detection_con=0.5, track_con=0.5):
        self.mode = mode
        self.max_hands = max_hands
        self.detection_con = detection_con
        self.track_con = track_con
        self.lock = threading.Lock()
            
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=self.mode,
            max_num_hands=self.max_hands,
            min_detection_confidence=self.detection_con,
            min_tracking_confidence=self.track_con
        )
        self.mp_draw = mp.solutions.drawing_utils
        
        # Device selection state
        self.selected_device = None
        self.device_selection_timeout = 10  # seconds
        self.device_selection_start = 0
        self.last_gesture_time = 0
        self.gesture_cooldown = 1.5  # seconds between gesture detections

    def find_hands(self, img, draw=True):
        with self.lock:
            try:
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                self.results = self.hands.process(img_rgb)
                
                if self.results.multi_hand_landmarks and draw:
                    for hand_landmarks in self.results.multi_hand_landmarks:
                        self.mp_draw.draw_landmarks(
                            img, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                return img
            except Exception as e:
                print(f"Hand detection error: {e}")
                return img

    def find_position(self, img, hand_no=0):
        lm_list = []
        with self.lock:
            if hasattr(self, 'results') and self.results.multi_hand_landmarks:
                if hand_no < len(self.results.multi_hand_landmarks):
                    my_hand = self.results.multi_hand_landmarks[hand_no]
                    h, w, c = img.shape
                    for id, lm in enumerate(my_hand.landmark):
                        cx, cy = int(lm.x * w), int(lm.y * h)
                        lm_list.append((id, cx, cy))
        return lm_list

    def is_palm_or_fist(self, lm_list, threshold=0.8):
        if not lm_list or len(lm_list) < 21:
            return None

        try:
            tips = [lm_list[i] for i in [8, 12, 16, 20]]  # Index to pinky tips
            mcp_joints = [lm_list[i] for i in [5, 9, 13, 17]]

            extended_fingers = 0
            for tip, mcp in zip(tips, mcp_joints):
                if tip[2] < mcp[2]:  # y-coord: lower on screen means finger is extended
                    extended_fingers += 1

            if extended_fingers >= 3:
                return "Palm"
            else:
                return "Fist"
        except Exception as e:
            print(f"Gesture detection error: {e}")
            return None

    def select_device(self, device):
        """Select a device for file transfer"""
        self.selected_device = device
        self.device_selection_start = time.time()

    def clear_selected_device(self):
        """Clear the selected device"""
        self.selected_device = None
        self.device_selection_start = 0

    def is_device_selected(self):
        """Check if a device is currently selected and not timed out"""
        if not self.selected_device:
            return False
        current_time = time.time()
        return (current_time - self.device_selection_start) < self.device_selection_timeout

    def get_selected_device(self):
        """Get the currently selected device"""
        return self.selected_device if self.is_device_selected() else None
