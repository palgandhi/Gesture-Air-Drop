import cv2
import mediapipe as mp
import threading

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
            # Check distance between fingertips and palm
            palm_base = lm_list[0]  # Wrist
            tips = [lm_list[i] for i in [8, 12, 16, 20]]  # Finger tips
            mcp_joints = [lm_list[i] for i in [5, 9, 13, 17]]  # Finger bases
            
            extended_fingers = 0
            for tip, mcp in zip(tips, mcp_joints):
                # Check if fingertip is above the MCP joint (finger extended)
                if tip[2] < mcp[2]:  # Comparing y-coordinates
                    extended_fingers += 1
            
            return "Palm" if extended_fingers >= 3 else "Fist"
        except Exception as e:
            print(f"Gesture detection error: {e}")
            return None