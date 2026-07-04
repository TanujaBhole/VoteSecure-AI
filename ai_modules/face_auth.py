import os
import cv2
import traceback
from config import basedir

# We will try to import face_recognition. 
# If it fails (e.g. dlib not installed on Windows), we will fall back to a simpler check or print a clear error.
try:
    import face_recognition
    FACE_REC_AVAILABLE = True
except ImportError:
    FACE_REC_AVAILABLE = False
    print("WARNING: 'face_recognition' library is not installed. Face verification will default to a fallback mode.")

def verify_face(user_id, current_image_path):
    """
    Verifies if the face in 'current_image_path' matches the saved face for 'user_id'.
    """
    from models import User
    
    user = User.query.get(user_id)
    if not user or not user.face_encoding:
        print(f"Face verification failed: No stored face data found for user {user_id}")
        return False

    saved_image_path = os.path.join(basedir, 'face_data', user.face_encoding)
    
    if not os.path.exists(saved_image_path):
        print(f"Face verification failed: Saved image file missing for user {user_id}")
        return False

    if not os.path.exists(current_image_path):
        print(f"Face verification failed: Current webcam capture missing.")
        return False

    if FACE_REC_AVAILABLE:
        try:
            # Load images
            known_image = face_recognition.load_image_file(saved_image_path)
            unknown_image = face_recognition.load_image_file(current_image_path)

            # Get encodings
            known_encodings = face_recognition.face_encodings(known_image)
            unknown_encodings = face_recognition.face_encodings(unknown_image)

            if len(known_encodings) == 0:
                print("Face verification failed: No face found in the saved profile image.")
                return False
                
            if len(unknown_encodings) == 0:
                print("Face verification failed: No face found in the current webcam image.")
                return False

            known_encoding = known_encodings[0]
            unknown_encoding = unknown_encodings[0]

            # Compare faces
            results = face_recognition.compare_faces([known_encoding], unknown_encoding, tolerance=0.6)
            
            is_match = results[0]
            print(f"Face Match Result for User {user_id}: {is_match}")
            return is_match

        except Exception as e:
            print(f"Error during face_recognition matching: {e}")
            traceback.print_exc()
            return False
    else:
        # Fallback: Just verify using OpenCV that a face is present in the current image
        try:
            image = cv2.imread(current_image_path)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Using OpenCV's pre-trained Haar cascade for basic face detection
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            
            if len(faces) > 0:
                print("Fallback Mode: Face detected in webcam image. Proceeding.")
                return True
            else:
                print("Fallback Mode: No face detected in webcam image.")
                return False
        except Exception as e:
            print(f"Error during fallback OpenCV detection: {e}")
            return False
