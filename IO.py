#!/usr/bin/env python
__author__ = 'jesse'

import os
import time
try:
    import rospy
    from bwi_speech_services.srv import *
    from bwi_perception.srv import *
    from segbot_arm_manipulation.srv import *
    from std_srvs.srv import *
    import roslib
    roslib.load_manifest('sound_play')
    from sound_play.libsoundplay import SoundClient
except ImportError:
    print "WARNING: cannot import ros-related libraries"
    rospy = None
    roslib = None


# Checks tokenization, adds possessive markers as own tokens, strips bad symbols
def process_raw_utterance(u):
    u = u.lower()
    tks = u.split()
    tks = [tk.strip() for tk in tks]
    to_add = []
    for idx in range(len(tks)):  # replace possession with recognized tokens
        if "'" in tks[idx] and tks[idx][0] != "'":  # contains apostrophe
            if tks[idx][-1] != "s":  # word ends like jess'
                tks[idx] = tks[idx][:-1]  # cut off apostrophe
            else:  # word ends like jesse's
                tks[idx] = tks[idx][:-2]  # cut off apostrophe s
            to_add.append([idx + 1, "'s"])
    for aidx in range(len(to_add)):
        idx, tk = to_add[aidx]
        tks.insert(idx + aidx, tk)
    tks = [tk.strip(',?.\"/\\!*&^%$#@()~+-') for tk in tks]
    u = ' '.join(tks)
    return u

# Perform input/output with the agent through the keyboard.
# This is good for a single user operating with a single instantiated, non-embodied agent.
class KeyboardIO:

    def __init__(self):
        pass

    # Get a string from the user.
    def get_from_user(self):
        print "YOU: "
        u = None
        while u is None or len(u) == 0:
            u = raw_input()
            u = process_raw_utterance(u)
        return u

    # Get an integer oidx from those provided or None.
    def get_oidx_from_user(self, oidxs):
        print "YOU POINT TO OIDX:"
        while True:  # until return happens
            u = raw_input()
            try:
                ui = int(u)
                if ui in oidxs:
                    return ui
            except ValueError:
                if 'none' in u or 'all' in u:
                    return None

    # Say a string to the user.
    def say_to_user(self, u):
        print "AGENT: " + u

    # Say a string with words aligned to ontological values.
    # u - a string utterance, possibly tagged with role-fill words like <p>this</p>
    # rvs - role values as a dictionary of roles -> strings
    # For KeyboardIO, this simply replaces the tags with the roll-fills and discards the filler text.
    def say_to_user_with_referents(self, u, rvs):
        for r in rvs:
            ts = "<" + r[0] + ">"
            te = "</" + r[0] + ">"
            if ts in u:
                pre_tag = u.split(ts)[0]
                post_tag = u.split(te)[1]
                u = pre_tag + rvs[r] + post_tag
        print "AGENT: " + u

    # Write out what action is taken given an action, patient, and recipient as strings.
    def perform_action(self, rvs):
        if rvs['action'] == 'walk':
            print "ROBOT ACTION: Navigate to location " + rvs['goal']
        elif rvs['action'] == 'bring':
            print "ROBOT ACTION: Pick up item " + rvs['patient'] + " and deliver it to person " + rvs['recipient']
        elif rvs['action'] == 'move':
            print "ROBOT ACTION: Move item " + rvs['patient'] + " from " + rvs['source'] + " to " + rvs['goal']
        else:
            raise ValueError("perform_action: unrecognized action '" + rvs['action'] + "'")


# Perform input/output with the agent through a Server.
# This is used to facilitate multiple Agents being managed through a central script, such as during
# Mechanical Turk experiments.
class SeverIO:

    # sever - a Server instance to communicate with.
    # id - a numerical id number to pass to the server for identification.
    # spin_time - seconds to spin between polling the server.
    def __init__(self, uid, client_dir, spin_time=1):
        self.uid = uid
        self.client_dir = client_dir
        self.spin_time = spin_time

    # Get a string from the user.
    # Polls the disk until a string message from the user appears.
    # Deletes the string message file from the disk.
    def get_from_user(self):
        path = os.path.join(self.client_dir, self.uid + '.smsgur.txt')  # request
        self._poll_for_file_write_contents(path, ' ')
        print "get_from_user requested feedback"

        path = os.path.join(self.client_dir, self.uid + '.smsgu.txt')
        u = self._poll_for_file_get_contents_delete(path)

        # Preprocess user utterance from the web.
        print "get_from_user (raw): '" + u + "'"
        u = process_raw_utterance(u)

        print "get_from_user (processed): '" + u + "'"
        return u

    # Get an integer oidx from those provided or None.
    # Polls the disk until an oidx message from the user appears.
    # Assumes that the file equals 'None' or an integer.
    # oidxs - not used in this implementation; insurance trusted from the client side
    def get_oidx_from_user(self, oidxs):
        path = os.path.join(self.client_dir, self.uid + '.omsgur.txt')  # request
        self._poll_for_file_write_contents(path, ' ')
        print "get_oidx_from_user requested feedback"

        path = os.path.join(self.client_dir, self.uid + '.omsgu.txt')
        u = self._poll_for_file_get_contents_delete(path)
        if u == 'None':
            u = None
        else:
            u = int(u)

        print "get_oidx_from_user: " + str(u)
        return u

    # Poll the disk for the specified file (blocking), get its contents and delete it from the disk.
    def _poll_for_file_get_contents_delete(self, fn):
        while not os.path.isfile(fn):
            time.sleep(self.spin_time)
        with open(fn, 'r') as f:
            u = f.read().strip()
        cmd = "rm -f " + fn
        os.system(cmd)
        return u

    # Say a string to the user.
    # This polls the disk until the existing message string is cleared, then writes the given new one.
    def say_to_user(self, u):
        path = os.path.join(self.client_dir, self.uid + '.smsgs.txt')
        self._poll_for_file_write_contents(path, u)
        print "say_to_user: " + str(u)

    # Say a string with words aligned to ontological values.
    # u - a string utterance, possibly tagged with role-fill words like <p>this</p>
    # rvs - role values as a dictionary of roles -> strings
    # This polls the disk until the existing referent message is cleared, then writes the given new one.
    def say_to_user_with_referents(self, u, rvs):
        path = os.path.join(self.client_dir, self.uid + '.rmsgs.txt')
        s = u + '\n' + ';'.join([str(r) + ':' + str(rvs[r]) for r in rvs])
        self._poll_for_file_write_contents(path, s)
        print "say_to_user_with_referents: " + str(u) + " " + str(rvs)

    # Write out what action is taken given an action, patient, and recipient as strings.
    # If the server already has a waiting one of these (which would be weird), poll until it clears.
    def perform_action(self, rvs):
        if rvs['action'] == 'walk':
            a_str = "The robot navigates to <g>here</g>."
        elif rvs['action'] == 'bring':
            a_str = "The robot finds <p>this</p> and delivers it to <r>this person</r>."
        elif rvs['action'] == 'move':
            a_str = "The robot moves <p>this</p> from <s>here</s> to <g>there</g>."
        elif rvs['action'] == 'init_phase':
            a_str = "Thanks!"
        else:
            a_str = "ERROR: unrecognized action for robot"
        path = os.path.join(self.client_dir, self.uid + '.amsgs.txt')
        s = a_str + '\n' + ';'.join([str(r) + ':' + str(rvs[r]) for r in rvs])
        self._poll_for_file_write_contents(path, s)
        print "perform_action: " + str(rvs)

    # Support functions:

    # Poll the disk for the specified file (blocking), and write it when it doesn't exist.
    def _poll_for_file_write_contents(self, fn, u):
        while os.path.isfile(fn):
            time.sleep(self.spin_time)
        with open(fn, 'w') as f:
            f.write(u)
        cmd = "chmod a+r " + fn
        os.system(cmd)
        return u


# Perform input/output with the agent through the arm segbot.
class RobotIO:

    def __init__(self, table_oidxs, starting_table, image_path=None,
                 voice="voice_cmu_us_slt_cg"):
        print "RobotIO: __init__ with " + str(table_oidxs) + ", " + str(starting_table) + ", " + voice
        self.table_oidxs = table_oidxs  # dictionary from table ids to lists of objects or None if there are None
        self.table = starting_table  # 1, 2, or 3. missing tables should have None as their table_oidxs
        self.image_path = image_path
        self.voice = voice
        self.last_say = None
        self.arm_pos = -1

        # initialize a sound client instance for TTS
        print "RobotIO: initializing SoundClient..."
        self.sound_client = SoundClient(blocking=True)
        rospy.sleep(1)
        self.sound_client.stopAll()
        print "RobotIO: ... done"

        rospy.wait_for_service('perceive_tabletop_scene')
        self.tabletop_object_detection_service = rospy.ServiceProxy('perceive_tabletop_scene',
                                                                    PerceiveTabletopScene, persistent=True)
        self.pointCloud2_plane = None
        self.cloud_plane_coef = None
        self.pointCloud2_objects = None

    # Listen for speech from user.
    def get_from_user(self):
        print "RobotIO: get_from_user called"
        self.listening_mode_toggle_client()
        uin = ''
        while len(uin) == 0:
            uin = self.sound_transcript_client()
            uin = process_raw_utterance(uin)
        self.listening_mode_toggle_client()

        if uin == "frozen fish":
            print "RobotIO: got shutdown keyphrase from user"
            raise rospy.ROSInterruptException

        print "RobotIO: get_from_user returning '" + uin + "'"
        return uin

    # Get an object touch or hear 'all' or 'none'
    # This call opens a sub-dialog in which the user can command the robot to face a different table,
    # watch for a touch, or answer that 'all' or 'none' of the objects fit the description
    # oidxs - not used in this implementation; oidxs drawn from table oidxs and current table face value
    # returns - an oidx in those provided or 'None'
    def get_oidx_from_user(self, oidxs):
        print "RobotIO: get_oidx_from_user called"

        self.point(-1)  # retract the arm, if it's out
        idx = -1
        while idx == -1:
            u = self.get_from_user()
            u = process_raw_utterance(u)
            ws = u.split()

            # The user asked the robot to face a different table.
            if "face" in ws:
                for ns, n in [("one", 1), ("1", 1), ("two", 2), ("2", 2)]:
                    if ns in ws:
                        if self.table != n:
                            self.face_table(n)
                        else:
                            self.say_to_user("I am already facing table " + str(n))
            elif "turn" in ws:
                if "left" in ws and self.table == 2:
                    self.face_table(1)
                elif "right" in ws and self.table == 1:
                    self.face_table(2)

            # The user told the robot to watch for a touch.
            elif "watch" in ws or "look" in ws or "this" in ws:
                idx = self.get_touch()

            # The user said "all" or "none"
            elif "all" in ws or "none" in ws:
                idx = None

            # The command couldn't be shallow parsed.
            else:
                self.say_to_user("Sorry, I didn't catch that.")
        self.say_to_user("I see.")
        if idx is not None:
            oidx = self.table_oidxs[self.table][idx]
        else:
            oidx = None

        print "RobotIO: get_oidx_from_user returning " + str(oidx)
        return oidx

    # use built-in ROS sound client to do TTS
    def say_to_user(self, s):
        print "RobotIO: say_to_user called with '" + s + "'"

        # Replace 'shake your head' lines for robot interface.
        shake_str = "shake your head"
        if shake_str in s:
            sidx = s.find(shake_str)
            if "you could use the word" in s:  # pos example
                new_str = "say 'none of them'"
            else:  # neg example
                new_str = "say 'all of them'"
            s = s[:sidx] + new_str + s[sidx + len(shake_str):]

        # Remove extra information in parens that was used during MTurk for robot interface.
        sidx = s.find("(")
        eidx = s.find(")") + 1
        while sidx > -1:
            s = s[:sidx] + s[eidx:]
            sidx = s.find("(")
            eidx = s.find(")") + 1

        if self.last_say is None:
            self.last_say = s
        else:
            self.last_say += " " + s

        self.sound_client.say(str(s), voice=self.voice)
        print "say_to_user: " + s

    # Say a string with words aligned to ontological values.
    # u - a string utterance, possibly tagged with role-fill words like <p>this</p>
    # rvs - role values as a dictionary of roles -> strings
    # This involves the robot naming rooms by number (source, goal), naming people (first names).
    # If a patient argument is present, points to that patient object
    # If the patient is not in the active training set (table_oidxs), throws an exception
    def say_to_user_with_referents(self, u, rvs):
        print "RobotIO: say_to_user_with_referents called with '" + u + "', " + str(rvs)

        # Replace recipients; we here hard-code the patients from the ispy setting, but, in general,
        # this should be a more interesting procedure.
        if 'recipient' in rvs and rvs['recipient'] is not None:
            p = None
            if rvs['recipient'] == 'b':
                p = 'robert'
            elif rvs['recipient'] == 'd':
                p = 'david'
            elif rvs['recipient'] == 'h':
                p = 'heidi'
            elif rvs['recipient'] == 'p':
                p = 'peggy'
            elif rvs['recipient'] == 'm':
                p = 'mallory'
            elif rvs['recipient'] == 'n':
                p = 'nancy'
            elif rvs['recipient'] == 'r':
                p = 'richard'
            elif rvs['recipient'] == 's':
                p = 'sybil'
            elif rvs['recipient'] == 'w':
                p = 'walter'
            sidx = u.find("<r>")
            eidx = u.find("</r>") + 4
            while sidx > -1:
                u = u[:sidx] + p + u[eidx:]
                sidx = u.find("<r>")
                eidx = u.find("</r>") + 4

        # Replace sources and goals. Here we assume all sources and goals are room numbers with possible
        # letter attachments a and b (because this is what happens in the ispy setting). To ease pronunciation
        # for the model, we space-delimit the numbers and letters.
        for r in ['source', 'goal']:
            if r in rvs and rvs[r] is not None:
                r0 = r[0]
                sidx = u.find("<" + r0 + ">")
                eidx = u.find("</" + r0 + ">") + 4
                while sidx > -1:
                    u = u[:sidx] + ' '.join(rvs[r]) + u[eidx:]
                    sidx = u.find("<" + r0 + ">")
                    eidx = u.find("</" + r0 + ">") + 4

        # Handle patient, which involves first turning to face the right table and pointing (blocking) before
        # releasing to speak.
        if 'patient' in rvs and rvs['patient'] is not None:
            sidx = u.find("<p>")
            eidx = u.find("</p>")

            if sidx > -1:  # if the robot actually said anything about the patient, point
                oidx = int(rvs['patient'].split('_')[1])  # e.g. 'oidx_1' -> 1
                ttid = None
                for tid in self.table_oidxs:
                    if self.table_oidxs[tid] is not None and oidx in self.table_oidxs[tid]:
                        ttid = tid
                if ttid is not None:
                    self.face_table(ttid)
                    self.point(self.table_oidxs[ttid].index(oidx))
                else:
                    raise IndexError("oidx " + str(oidx) + " not found on tables")

            # Strip <p> </p> from utterance, but speak words between.
            while sidx > -1:
                u = u[:sidx] + u[sidx + 3:eidx] + u[eidx + 4:]
                sidx = u.find("<p>")
                eidx = u.find("</p>")

        # Speak the utterance with all roles instantiated, and possible pointing initiated.
        self.say_to_user(u)

    # Take in an action as a role-value-slot dictionary and produce robot behavior.
    # TODO: this needs to next be tied to actual robot performing behavior
    def perform_action(self, rvs):
        print "RobotIO: perform_action called with " + str(rvs)
        cmd = None
        if rvs['action'] == 'walk':
            a_str = "I will navigate to <g>here</g>."
        elif rvs['action'] == 'bring':
            a_str = "I will grab the object and deliver it to <r>this person</r>."
            if self.image_path is not None:
                cmd = "eog " + os.path.join(self.image_path, rvs['patient'] + ".jpg")
        elif rvs['action'] == 'move':
            a_str = "I will relocate the object from <s>here</s> to <g>there</g>."
            if self.image_path is not None:
                cmd = "eog " + os.path.join(self.image_path, rvs['patient'] + ".jpg")
        else:
            raise ValueError("unrecognized action type to perform '" + rvs['action'] + "'")

        # Speak, retract arm, show image of target object (if relevant)
        self.say_to_user_with_referents(a_str, rvs)
        self.point(-1)  # retract arm
        if cmd is not None:
            os.system(cmd)

        # Turn to face 'table 3' (empty space) to facilitate navigation
        self.face_table(3, verbose=False)
        # TODO: execute the action on the physical robot platform

    # Support functions:

    # get touches by detecting human touches on top of objects
    def get_touch(self):
        print "RobotIO support: get_touch called"
        if self.pointCloud2_plane is None:
            self.say_to_user("I am getting the objects on the table into focus.")
            self.pointCloud2_plane, self.cloud_plane_coef, self.pointCloud2_objects = self.obtain_table_objects()
            self.say_to_user("Okay, I see them.")
        self.watching_mode_toggle_client()
        idx = self.detect_touch_client()
        self.watching_mode_toggle_client()
        print "RobotIO support: get_touch returning " + str(idx)
        return int(idx)

    # point using the robot arm
    def point(self, idx):
        print "RobotIO support: point called with " + str(idx)
        if self.arm_pos != idx:
            if self.pointCloud2_plane is None and idx != -1:
                self.say_to_user("I am getting the objects on the table into focus.")
                self.pointCloud2_plane, self.cloud_plane_coef, self.pointCloud2_objects = self.obtain_table_objects()
                self.say_to_user("Okay, I see them.")
            self.touch_client(idx)
        self.arm_pos = idx

    # Rotate the chassis and establish new objects in line of sight.
    def face_table(self, tid, verbose=True):
        print "RobotIO support: face_table called with " + str(tid)
        self.point(-1)  # retract the arm, if it's out
        if tid != self.table:
            if verbose:
                self.say_to_user("I am turning to face table " + str(tid) + ".")
            s = self.face_table_client(tid)
            self.table = tid
            self.pointCloud2_plane = None
            self.cloud_plane_coef = None
            self.pointCloud2_objects = None
            print "RobotIO support: face_table returning " + str(s)
        else:
            s = True
        return s

    # get the point cloud objects on the table for pointing / recognizing touches
    def obtain_table_objects(self):
        print "RobotIO support: obtain_table_objects called"
        plane = plane_coef = cloud_objects = None
        focus = False
        while not focus:
            tries = 5
            while tries > 0:
                plane, plane_coef, cloud_objects = self.get_pointCloud2_objects()
                if len(cloud_objects) == len(self.table_oidxs[self.table]):
                    focus = True
                    break
                tries -= 1
                rospy.sleep(1)
            if tries == 0 and not focus:
                self.say_to_user("I am having trouble focusing on the objects.")
                rospy.sleep(10)
        print "RobotIO support: obtain_table_objects returning plane/coef/objects"
        return plane, plane_coef, cloud_objects

    # get PointCloud2 objects from service
    def get_pointCloud2_objects(self):
        print "RobotIO support: get_pointCloud2_objects called"

        # query to get the blobs on the table
        req = PerceiveTabletopSceneRequest()
        req.apply_x_box_filter = True  # limit field of view to table in front of robot
        req.x_min = -0.25
        req.x_max = 0.8
        try:
            res = self.tabletop_object_detection_service(req)

            if len(res.cloud_clusters) == 0:
                return [], [], []

            # re-index clusters so order matches left-to-right indexing expected
            ordered_cloud_clusters = self.reorder_client(res.cloud_clusters, "x", True)

            print ("RobotIO support: get_pointCloud2_objects returning res with " +
                   str(len(ordered_cloud_clusters)) + " clusters")
            return res.cloud_plane, res.cloud_plane_coef, ordered_cloud_clusters
        except rospy.ServiceException, e:
            sys.exit("Service call failed: %s " % e)

    # ROS client functions:

    # Turn on or off the indicator behavior for listening for speech.
    def listening_mode_toggle_client(self):
        print "RobotIO client: listening_mode_toggle_client called"
        rospy.wait_for_service('ispy/listening_mode_toggle')
        try:
            listen_toggle = rospy.ServiceProxy('ispy/listening_mode_toggle', Empty)
            listen_toggle()
        except rospy.ServiceException, e:
            sys.exit("Service call failed: %s " % e)

    # Turn on or off the indicator behavior for watching for touch.
    def watching_mode_toggle_client(self):
        print "RobotIO client: watching_mode_toggle_client called"
        rospy.wait_for_service('ispy/touch_waiting_mode_toggle')
        try:
            watch_toggle = rospy.ServiceProxy('ispy/touch_waiting_mode_toggle', Empty)
            watch_toggle()
        except rospy.ServiceException, e:
            sys.exit("Service call failed: %s " % e)

    # Listen for speech, transcribe it, and return it.
    def sound_transcript_client(self):
        print "RobotIO client: sound_transcript_client called"

        rospy.wait_for_service('sound_transcript_server')
        try:
            transcribe = rospy.ServiceProxy('sound_transcript_server', RequestSoundTranscript)
            resp = transcribe()
            if not resp.isGood:
                return ''
            return resp.utterance
        except rospy.ServiceException, e:
            print "Service call failed: %s " % e
            return ''

    # Turn in place to face a new table.
    def face_table_client(self, tid):
        print "RobotIO client: face_table_client called with " + str(tid)
        req = iSpyFaceTableRequest()
        req.table_index = tid
        rospy.wait_for_service('ispy/face_table')
        try:
            face = rospy.ServiceProxy('ispy/face_table', iSpyFaceTable)
            res = face(req)
            return res.success
        except rospy.ServiceException, e:
            sys.exit("Service call failed: %s" % e)

    # reorder PointCloud2 objects returned in arbitrary order from table detection
    def reorder_client(self, clouds, axis, forward):
        print "RobotIO client: reorder_client called with " + str(axis) + ", " + str(forward)
        req = iSpyReorderCloudsRequest()
        req.axis = axis
        req.forward = forward
        req.clouds = clouds
        req.frame_id = "arm_link"
        rospy.wait_for_service('ispy/reorder_clouds')
        try:
            reorder = rospy.ServiceProxy('ispy/reorder_clouds', iSpyReorderClouds)
            res = reorder(req)
            return res.ordered_clouds
        except rospy.ServiceException, e:
            sys.exit("Service call failed: %s " % e)

    # use the arm to touch an object
    def touch_client(self, idx):
        print "RobotIO client: touch_client called with " + str(idx)
        req = iSpyTouchRequest()
        req.cloud_plane = self.pointCloud2_plane
        req.cloud_plane_coef = self.cloud_plane_coef
        req.objects = self.pointCloud2_objects
        req.touch_index = idx
        rospy.wait_for_service('ispy/touch_object_service')
        try:
            touch = rospy.ServiceProxy('ispy/touch_object_service', iSpyTouch)
            res = touch(req)
            return res.success
        except rospy.ServiceException, e:
            print "Service call failed: %s" % e

    # detect a touch above an object
    def detect_touch_client(self):
        print "RobotIO client: detect_touch_client called"
        req = iSpyDetectTouchRequest()
        req.cloud_plane = self.pointCloud2_plane
        req.cloud_plane_coef = self.cloud_plane_coef
        req.objects = self.pointCloud2_objects
        rospy.wait_for_service('ispy/human_detect_touch_object_service')
        try:
            detect_touch = rospy.ServiceProxy('ispy/human_detect_touch_object_service', iSpyDetectTouch)
            res = detect_touch(req)
            return res.detected_touch_index
        except rospy.ServiceException, e:
            print "Service call failed: %s" % e
