<html>
<head>
<title>Command a Robot</title>

<!-- First include jquery js -->
<script src="//code.jquery.com/jquery-1.12.0.min.js"></script>
<script src="//code.jquery.com/jquery-migrate-1.2.1.min.js"></script>

<!-- Latest compiled and minified JavaScript -->
<script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/js/bootstrap.min.js" integrity="sha384-Tc5IQib027qvyjSMfHjOMaLkfuWVxZxUPnCJA7l2mCWNIpG9mGCD8wGNIcPD7Txa" crossorigin="anonymous"></script>

<!-- Latest compiled and minified CSS -->
<link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css" integrity="sha384-BVYiiSIFeK1dGmJRAkycuHAHRg32OmUcww7on3RYdg4Va+PmSTsz/K68vbdEjh4u" crossorigin="anonymous">

<link rel="stylesheet" href="style.css">

<script type="text/javascript">
// Global vars for the script.
var iv;  // the interval function that polls for robot response.
var num_user_turns = 0;  // the number of dialog turns the user has taken
var num_polls_since_last_message = 0;  // the number of times we've polled and gotten no response
// urls the agent uses to communicate with this user
var smsgs_url;
var rmsgs_url;
var amsgs_url;
var smsgur_url;
var omsgur_url;

// Functions that don't access the server or the client-side display.

// Enable the survey submit button if all radio buttons have been checked.
function enable_survey_submit() {
  var names = ["tasks_easy", "understood", "frustrated", "object_qs", "use_navigation", "use_delivery", "use_relocation"];
  var all_checked = true;
  var idx;
  for (idx = 0; idx < names.length; idx++) {
    if (!$("input[name='" + names[idx] + "']:checked").val()) {
      all_checked = false;
      break;
    }
  }
  if (all_checked) {
    $('#survey_submit_button').prop("disabled", false);
  }
}

// Given a referent message, recolor it and fill the appropriate interface panels.
function process_referent_message(c) {
  var ca = c.split('\n');
  
  // Fill interface panels.
  clear_panels('interface');
  var roles = ca[1].split(';');
  var i;
  for (i=0; i < roles.length; i++) {
    ra = roles[i].split(':');
    if (ra[1] != "None") {
      fill_panel('interface', ra[0], ra[1]);      
    }
  }

  // Recolor message.
  var m = ca[0];
  m = m.replace("<p>", "<span class=\"patient_text\">");
  m = m.replace("<r>", "<span class=\"recipient_text\">");
  m = m.replace("<s>", "<span class=\"source_text\">");
  m = m.replace("<g>", "<span class=\"goal_text\">");
  m = m.replace("</p>", "</span>");
  m = m.replace("</r>", "</span>");
  m = m.replace("</s>", "</span>");
  m = m.replace("</g>", "</span>");
  return m;
}

// Given a referent message, return the roles as their self-same string.
function get_roles_from_referent_message(c) {
  var ca = c.split('\n');
  return ca[1];
}

// Functions related to manipulating the actual interface and running the task.

// Show an error in the error div.
function show_error(e) {
  $('#err').show();
  $('#err_text').html(e);
}

// Enable the user text input.
function enable_user_text() {
  $('#user_input').prop("disabled", false);
  $('#user_input').focus();
  $('#user_say').prop("disabled", false);
}

// Disable user text input.
function disable_user_text() {
  $('#user_input').prop("disabled", true);
  $('#user_say').prop("disabled", true);
}

// Enable the user to see and interact with the nearby object buttons.
function enable_user_train_object_answer() {
  $('#nearby_objects_div').prop("hidden", false);
}

// Disable the user from the nearby object buttons.
function disable_user_train_object_answer() {
  $('#nearby_objects_div').prop("hidden", true);
}

// Hide all the panels.
// type - either 'task' or 'interface'
function clear_panels(type) {
  $('#' + type + "_patient_panel").prop("hidden", true);
  $('#' + type + "_recipient_panel").prop("hidden", true);
  $('#' + type + "_source_panel").prop("hidden", true);
  $('#' + type + "_goal_panel").prop("hidden", true);
}

// Fill a panel with an image.
// type - either 'task' or 'interface'
// role - one of 'patient', 'recipient', 'source', or 'goal'
// atom - the ontological atom used to find the corresponding image for the panel
function fill_panel(type, role, atom) {
  if (role == "recipient") {
    atom = atom.toUpperCase(); // because people names are capitalized in pngs for some reason
    var rd = "people/";
    var ext = "png";
    var img_class = "person_img";
    var va = true;
  } else if (role == "source" || role == "goal") {
    var rd = "maps/";
    var ext = "png";
    var img_class = "map_img";
    var va = false;
  } else if (role == "patient") {
    var rd = "objects/";
    var ext = "jpg";
    var img_class = "obj_img";
    var va = true;
  }
  var fn = "images/" + rd + atom + "." + ext;
  var content = "<img src=\"" + fn + "\" class=\"" + img_class + "\">";
  if (va) {
    content = "<span class=\"va\"></span>" + content;
  }
  $('#' + type + '_' + role + '_panel').html(content);
  $('#' + type + '_' + role + '_panel').prop("hidden", false);
  if (!va && type == 'task' && role == "goal") {  // maps are present (walk and move tasks)
    var task_text = $('#task_text').html();
    task_text += "<br/>Letters in offices indicate that the corresponding person owns that office.";
    $('#task_text').html(task_text);
  }
}

// Unhighlight all nearby objects.
function nearby_objects_clear_all() {
  for (var idx = 0; idx < 8; idx++) {
    $('#robot_obj_' + idx).removeClass("robot_obj_panel_highlight");
  }
}

function nearby_objects_highlight(idx) {
  $('#robot_obj_' + idx).removeClass("robot_obj_panel");
  $('#robot_obj_' + idx).addClass("robot_obj_panel_highlight");
}

function nearby_objects_clear(idx) {
  $('#robot_obj_' + idx).removeClass("robot_obj_panel_highlight");
  $('#robot_obj_' + idx).addClass("robot_obj_panel");
}

// Remove all rows from the dialog table except the user input row.
function clear_dialog_table() {
  $("#dialog_table > tr").slice($('#dialog_table tr').length - 1).remove();
}

// Delete the specified row from the dialog table.
// i - and index. if negative, will subtract from length.
function delete_row_from_dialog_table(i) {
  var table = document.getElementById('dialog_table');
  if (i < 0) {
    var base = table.rows.length;
  } else {
    var base = 0;
  }
  table.deleteRow(base + i);
}

// Add a new row to the bottom of the dialog table.
// m - the string message to add
// u - true if message is from the user, false otherwise
// i - the position at which to add the row (expected negative)
function add_row_to_dialog_table(m, u, i) {
  var table = document.getElementById('dialog_table');
  var row = table.insertRow(table.rows.length - 1 + i);
  var name_cell = row.insertCell(0);
  var msg_cell = row.insertCell(1);
  if (u) {
    name_cell.innerHTML = "YOU";
    var row_class = "user_row";
  } else {
    name_cell.innerHTML = "ROBOT";
    var row_class = "robot_row";
    m = m.replace("not", "<b>not</b>");  // bold the word 'not' in robot utterances
  }
  row.className = row_class;
  msg_cell.innerHTML = m;
}

// Get user input text and send it to the agent.
// d - the directory
// uid - user id
function send_agent_user_text_input(d, uid) {
  disable_user_text();
  var m = $('#user_input').val();  // read the value
  $('#user_input').val('');  // clear user text
  add_row_to_dialog_table(m, true, 0);  // add the user text to the dialog table history
  send_agent_string_message(d, uid, m, false);  // send user string message to the agent
  show_agent_thinking();
  increment_user_turns();
}

// Get user oidx point and send it to the agent.
// point - the object pointed to or "None"
// d - the directory
// uid - user id
function send_agent_user_oidx_input(point, d, uid) {
  disable_user_train_object_answer();
  if (point == "None") {
    add_row_to_dialog_table("*you shake your head*", true, 0);
  } else {
    add_row_to_dialog_table("*you point*", true, 0);
  }
  send_agent_string_message(d, uid, point, true);  // send user string message to the agent
  show_agent_thinking();
  increment_user_turns();
}

// Increment the number of dialog turns the user has made.
// If the number of turns exceeds a threshold, offer the user the option
// to advance to payment (in case dialog gets super wonky).
function increment_user_turns() {
  num_user_turns += 1;
  if (num_user_turns >= 30) {
    $('#skip_to_end').prop("hidden", false);
    $('#dialog_too_long_div').prop("hidden", false);
  }
}

// Write a string message to disk for the server to pick up.
// d - the directory where messages live
// uid - the user id
// m - the string message to write to file
// om - whether this is an object message (true/false)
function send_agent_string_message(d, uid, m, om) {
  if (!om) {
    var fn = d + uid + ".smsgu.txt";
  } else {
    var fn = d + uid + ".omsgu.txt";
  }
  var url = "manage_files.php?opt=write&fn=" + fn + "&m=" + encodeURIComponent(m);
  var success = http_get(url);
  if (success == "0") {
    show_error("Failed to write file '" + fn + "' with message contents '" + m + "'.<br>Attempt made with url '" + url + "'.");
  }
}

// Disables user feedback and adds the "thinking" row for the agent.
function show_agent_thinking() {
  disable_user_text();  // disable user input from typing
  add_row_to_dialog_table("<i>thinking...</i>", false, 0);
}

function poll_for_agent_messages() {

  // Increment time so far if user is unable to respond.
  if ($('#user_say').prop("disabled") && $('#nearby_objects_div').prop("hidden")) {
    num_polls_since_last_message += 1;
  }

  // Check for an action message.
  var contents = get_and_delete_file(amsgs_url);
  if (contents) {
    delete_row_from_dialog_table(-2);  // delete 'thinking'
    var m = process_referent_message(contents);
    $('#action_text').html(m)
    $('#finished_task_div').show();  // show advance to next task button
    var roles = get_roles_from_referent_message(contents);
    $('#action_chosen_post').val(roles);  // the roles chosen for the action
    disable_user_text();  // just in case
    disable_user_train_object_answer();  // just in case
    $('#skip_to_end').prop("hidden", true);  // /just in case
    num_polls_since_last_message = 0;
    num_user_turns = 0;
    clearInterval(iv);

    // We need to return early here because the Agent is fast and has likely already booted
    // up the next dialog and sent the greeting message and user request. Instead of eating
    // those here and ending the client-side dialog, we return until this function is set
    // up for polling again.
    return;
  }

  // Check for string or referent messages.
  populate_from_string_or_referent_messages(smsgs_url, rmsgs_url);

  // Check for a request for user messages.
  contents = get_and_delete_file(smsgur_url);
  if (contents) {  // string message request
    delete_row_from_dialog_table(-2);  // delete 'thinking'
    enable_user_text();
    num_polls_since_last_message = 0;
  }
  contents = get_and_delete_file(omsgur_url);
  if (contents) {  // oidx message request
    delete_row_from_dialog_table(-2);  // delete 'thinking'
    enable_user_train_object_answer();
    num_polls_since_last_message = 0;
  }

  // We poll every 5 seconds (5000 ms); if polling has gone on with no messages for
  // two minutes, allow skipping.
  if (num_polls_since_last_message * 5 > 60 * 2) {
    $('#skip_to_end').prop("hidden", false);
    $('#robot_unresponsive_div').prop("hidden", false);
  }
}

// Check fo string or referent messages.
function populate_from_string_or_referent_messages(smsgs_url, rmsgs_url) {

  var contents = get_and_delete_file(smsgs_url);
  if (contents) {
    add_row_to_dialog_table(contents, false, -1);
    num_polls_since_last_message = 0;
  }

  // Check for a referent message.
  contents = get_and_delete_file(rmsgs_url);
  if (contents) {
    var m = process_referent_message(contents);
    add_row_to_dialog_table(m, false, -1);
    num_polls_since_last_message = 0;
  }
}

// Sample a task corresponding to the number and give it to the user.
function show_task(d, uid, action, patient, recipient, source, goal) {
  $('#next_task_div').hide();  // hide next task div
  clear_dialog_table();  // Clear the dialog history.

  // Sample a task of the matching number.
  var prob_form = "Command the robot with a complete sentence. ";
  prob_form += "The robot does not understand questions, but it may ask you questions of its own. ";
  prob_form += "The robot understands high-level commands, so it doesn't need step-by-step instructions, and it doesn't matter what location it starts in. "
  prob_form += "<br/><br/>Give the robot a command to solve this problem:";
  if (action == 'move') {
    var task_text = "<p><b>" + prob_form + "<br><span class=\"patient_text\">The object</span> shown below is at the X marked on the <span class=\"source_text\">pink map</span>. The object belongs at the X marked on the <span class=\"goal_text\">green map</span>.</b></p>";
  } else if (action == 'bring') {
    var task_text = "<p><b>" + prob_form + "<br><span class=\"recipient_text\">This person</span> needs <span class=\"patient_text\">the object</span> shown below.</b></p>";
  } else if (action == 'walk') {
    var task_text = "<p><b>" + prob_form + "<br>The robot should be at the X marked on the <span class=\"goal_text\">green map</span>.</b></p>";
  }

  // Render the task on the display.
  $('#task_text').html(task_text);
  if (patient) {
    fill_panel("task", "patient", patient);
  }
  if (recipient) {
    fill_panel("task", "recipient", recipient);
  }
  if (source) {
    fill_panel("task", "source", source);
  }
  if (goal) {
    fill_panel("task", "goal", goal);
  }

  // Get first message from robot and unhide display.
  $('#interaction_div').show();
  show_agent_thinking(d, uid);

  // Start infinite, 5 second poll for robot feedback that ends when action message is shown.
  smsgs_url = d + uid + ".smsgs.txt";
  rmsgs_url = d + uid + ".rmsgs.txt";
  amsgs_url = d + uid + ".amsgs.txt";
  smsgur_url = d + uid + ".smsgur.txt";
  omsgur_url = d + uid + ".omsgur.txt";
  iv = setInterval(poll_for_agent_messages, 5000);
}

// Functions related to server-side processing.

// Get the contents of the given url, then delete the underlying file.
// url - url to get from and then delete
// returns - the contents of the url page
function get_and_delete_file(url) {
  var read_url = "manage_files.php?opt=read&fn=" + encodeURIComponent(url) + "&v=" + Math.floor(Math.random() * 999999999).toString();
  var contents = http_get(read_url);
  if (contents == "0") {  // file not written
    return false;
  } else {

    // delete the read file
    var del_url = "manage_files.php?opt=del&fn=" + encodeURIComponent(url);
    success = http_get(del_url);
    if (success == "0") {
      show_error("Failed to delete file '" + url + "' using url '" + del_url + "'.");
    }

    return contents;
  }
}

// Get the contents of the given url.
// url - said url
// Implementation from: https://stackoverflow.com/questions/247483/http-get-request-in-javascript
function http_get(url)
{
    var xmlHttp = new XMLHttpRequest();
    xmlHttp.open("GET", url, false); // false for synchronous request
    xmlHttp.send(null);
    return xmlHttp.responseText;
}

// Check whether the given url returns a 404.
// url - the url to check
// returns bool
function url_exists(url) {
  var check_url = "manage_files.php?opt=exists&fn=" + encodeURIComponent(url);
  var exists = http_get(check_url);
  if (exists == "1") {
    return true;
  } else {
    return false;
  }
}

</script>

</head>

<body>
<div id="container">

<div class="row" id="err" style="display:none;">
  <div class="col-md-1"></div>
  <div class="col-md-10" id="err_text"></div>
  <div class="col-md-1"></div>
</div>

<?php
require_once('functions.php');

# Variables that control what tasks and objects will be shown.
# These should be changed whenever a new Turk task is made.
$fold = 2;  # out of 0, 1, 2. Fold 3 is reserved as the test fold always.
$setting = "train";  # either init, train, or test

$d = 'client/';
$active_train_set = get_active_train_set($fold);
shuffle($active_train_set);

# This is a new landing, so we need to set up the task and call the Server to make an instance.
if (!isset($_POST['uid'])) {
  $uid = uniqid();

  # Show instructions.
  $inst = "<p>In this HIT, you will command a robot to perform several tasks. ";
  $inst .= "The robot is learning, and will ask you to reword your commands ";
  $inst .= "and help it better understand which words apply to physical objects. ";
  $inst .= "After three tasks, you will complete a short survey about your experience.</p>";
  # $inst .= "<p>You will receive a <b>payment bonus</b> for <b>each correctly completed</b> ";
  # $inst .= "task out of the three. If the robot completes all three tasks correctly, your ";
  # $inst .= "payment will be <b>doubled</b> (This bonus may take a few days to come through.)</p>";
  $inst .= "<p>Once you start the HIT, <b>do not refresh or navigate away from this page</b> ";
  $inst .= "until you reach the end and claim your payment code for Mechanical Turk.</p><br/>";
  ?>
  <div class="row" id="inst_div">
    <div class="col-md-12">
      <?php echo $inst;?>
      <form action="index.php" method="POST">
        <input type="hidden" name="uid" value="<?php echo $uid;?>">
        <input type="hidden" name="task_num" value="1">
        <input type="submit" class="btn" value="Okay">
      </form>
    </div>
  </div>
  <?php
}

# This is a return landing, so load a task and show the interface.
else {

  $uid = $_POST['uid'];
  $task_num = $_POST['task_num'];
  $action_chosen = $_POST['action_chosen'];
  $too_long = $_POST['too_long'];

  # Write a new user file so the Server creates an Agent assigned to this uid.
  if ($task_num == 1) {
    $fn = $d . $uid . '.newu.txt';
    write_file($fn, ' ', 'Could not create file to request new dialog agent.');
  }

  # If this is a subseqent task, write out the completed action to appropriate logfile.
  if ($task_num > 1 && $too_long != 1) {
    $fn = 'user_data/' . $uid . '.' . ($task_num - 1) . '.chosen.txt';
    $err_msg = "Failed to write action chosen " . $action_chosen . " to file " . $fn;
    write_file($fn, $action_chosen, $err_msg);
  }

  # If this is the end, advance to the survey instead.
  if ($task_num == 4) {
    ?>
    <div id="survey_div">
      <div class="row">
        <div class="col-md-12">
          <form action="generate_code.php" method="POST">
            <input type="hidden" name="uid" value="<?php echo $uid;?>">
            <table class="dialog_table">
              <tr>
                <td>&nbsp;</td><td style="text-align:center">Strongly Disagree</td><td style="text-align:center">Disagree</td><td style="text-align:center">Slightly Disagree</td><td style="text-align:center">Neutral</td><td style="text-align:center">Slightly Agree</td><td style="text-align:center">Agree</td><td style="text-align:center">Strongly Agree</td>
              </tr>
              <?php
                $qs = array("The tasks were easy to understand.", "The robot understood me.", "The robot frustrated me.", "The robot asked too many questions about objects.", "I would use a robot like this to help navigate a new building.", "I would use a robot like this to get items for myself or others.", "I would use a robot like this to move items from place to place.");
                $names = array("tasks_easy", "understood", "frustrated", "object_qs", "use_navigation", "use_delivery", "use_relocation");
                for ($idx = 0; $idx < count($qs); $idx ++) {
                  $tr_class = ($idx % 2 == 0) ? "robot_row" : "user_row";
                  echo "<tr class=\"" . $tr_class . "\"><td>" . $qs[$idx] . "</td>";
                  for ($l = 0; $l < 7; $l ++) {
                    echo "<td style=\"text-align:center\"><input type=\"radio\" name=\"" . $names[$idx] . "\" value=\"" . $l . "\" onclick=\"enable_survey_submit()\"></td>";
                  }
                  echo "</tr>";
                }
              ?>
            </table>
            Feel free to leave any comments you have about your experience here (optional):
            <textarea rows="4" cols="50" maxlength="512" name="open_response"></textarea>
            <input type="submit" class="btn" id="survey_submit_button" value="Submit responses and get Mechanical Turk code" disabled>
          </form>
        </div>
      </div>
    </div>
    <?php
  }

  # Still tasks to do.
  else {

    # Draw a task based on the number.
    # task_roles is a dictionary of roles -> targets for relevant roles.
    $task_roles = draw_task($task_num, $setting);
    $action = $task_roles['action'];
    $patient = (array_key_exists('patient', $task_roles) ? $task_roles['patient'] : false);
    $recipient = (array_key_exists('recipient', $task_roles) ? $task_roles['recipient'] : false);
    $source = (array_key_exists('source', $task_roles) ? $task_roles['source'] : false);
    $goal = (array_key_exists('goal', $task_roles) ? $task_roles['goal'] : false);

    # Write drawn task to file.
    $fn = 'user_data/' . $uid . '.' . $task_num . '.drawn.txt';
    $drawn_roles = array();
    foreach ($task_roles as $r => $v) {
      $drawn_roles[] = $r . ":" . $v;
    }
    $data = implode(";", $drawn_roles);
    $err_msg = "Failed to write drawn task " . $data . " to file " . $fn;
    write_file($fn, $data, $err_msg);

    # Show the goal and interface rows.
    ?>
    <div id="interaction_div" style="display:none;">
      <div class="row">
        <div class="col-md-12" id="task_text"></div>
      </div>
      <div class="row">
        <div class="col-md-8">
          <div class="row">
            <div class="col-md-1 patient_panel" id="task_patient_panel" hidden></div>
            <div class="col-md-1 recipient_panel" id="task_recipient_panel" hidden></div>
            <div class="col-md-1 source_panel" id="task_source_panel" hidden></div>
            <div class="col-md-1 goal_panel" id="task_goal_panel" hidden></div>
          </div>
        </div>
        <div class="col-md-4">
          <table id="person_directory" class="dialog_table">
            <thead><tr><th>Person</th><th>Name</th></tr></thead>
            <tbody>
              <tr><td><img src="images/people/B.png"></td><td>Robert "Bob" Brown</td></tr>
              <tr><td><img src="images/people/D.png"></td><td>David "Dave" Daniel</td></tr>
              <tr><td><img src="images/people/H.png"></td><td>Dr. Heidi Hughes</td></tr>
              <tr><td><img src="images/people/M.png"></td><td>Mallory "Mal" Maroon</td></tr>
              <tr><td><img src="images/people/N.png"></td><td>Dr. Nancy Nagel</td></tr>
              <tr><td><img src="images/people/P.png"></td><td>Peggy Parker, Intern</td></tr>
              <tr><td><img src="images/people/R.png"></td><td>Richard Rogue, Secretary</td></tr>
              <tr><td><img src="images/people/S.png"></td><td>Dr. Sybil Smalt</td></tr>
              <tr><td><img src="images/people/W.png"></td><td>Walter Ward, Supervisor</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <hr>

      <div class="row">
        <div class="col-md-6">
          <div>
            <table id="dialog_table" class="dialog_table"><tbody>
              <tr id="user_input_row"><td class="user_row">YOU</td><td><input type="text" id="user_input" style="width:100%;" placeholder="type your response here..." onkeydown="if (event.keyCode == 13) {$('#user_say').click();}"></td></tr>
            </tbody></table>
            <button class="btn" id="user_say" onclick="send_agent_user_text_input('<?php echo $d;?>', '<?php echo $uid;?>')">Say</button>
          </div>
          <div id="finished_task_div" hidden>
            <div id="action_text"></div>
            To advance to the next task, click the button below.
              <form action="index.php" method="POST">
                <input type="hidden" name="uid" value="<?php echo $uid;?>">
                <input type="hidden" name="task_num" value="<?php echo $task_num + 1;?>">
                <input type="hidden" name="too_long" value="0">
                <input type="hidden" id="action_chosen_post" name="action_chosen" value="">
                <input type="submit" class="btn" value="Okay">
              </form>
          </div>
          <div id="skip_to_end" hidden>
            </hr>
            <div id="dialog_too_long_div" hidden>
              <p>This conversation has gotten pretty long! If you'd like to prematurely end the task, you can do so by clicking the button below. Feel free to continue chatting with the robot, though!</p>
            </div>
            <div id="robot_unresponsive_div" hidden>
              <p>It looks like the robot might have encountered a problem. If you'd like to end the task and advance to payment, you can do so by clicking the button below.</p>
            </div>
            <form action="index.php" method="POST">
              <input type="hidden" name="uid" value="<?php echo $uid;?>">
              <input type="hidden" name="task_num" value="4">
              <input type="hidden" name="too_long" value="1">
              <input type="hidden" id="action_chosen_post" name="action_chosen" value="">
              <input type="submit" class="btn" value="End task and take survey">
            </form>
          </div>
        </div>
        <div class="col-md-6">
          <div id="nearby_objects_div" hidden>
            <?php
              echo "<div class=\"col-md-1 robot_obj_panel\"><span class=\"va\"></span><button class=\"btn robot_obj_btn\" onclick=\"send_agent_user_oidx_input('None', '" . $d . "', '" . $uid . "')\">Shake Head</button></div>";
              for ($idx = 0; $idx < count($active_train_set); $idx++) {
                echo "<div class=\"col-md-1 robot_obj_panel\" id=\"robot_obj_" . $idx ."\" onmouseover=\"nearby_objects_highlight('" . $idx . "')\" onmouseleave=\"nearby_objects_clear('" . $idx . "')\">";
                $oidx = explode('_', $active_train_set[$idx])[1];
                echo "<span class=\"va\"></span><img src=\"images/objects/" . $active_train_set[$idx] . ".jpg\" class=\"obj_img\" onclick=\"{nearby_objects_clear_all(); nearby_objects_highlight('" . $idx . "'); send_agent_user_oidx_input('" . $oidx . "', '". $d . "', '" . $uid . "');}\">";
                echo "</div>";
              }
            ?>
          </div>
          <div>
            <div class="row">
            <span class="align-bottom">
              <div class="col-md-1 patient_panel" id="interface_patient_panel" hidden></div>
              <div class="col-md-1 recipient_panel" id="interface_recipient_panel" hidden></div>
              <div class="col-md-1 source_panel" id="interface_source_panel" hidden></div>
              <div class="col-md-1 goal_panel" id="interface_goal_panel" hidden></div>
            </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="row" id="next_task_div">
      <div class="col-md-12">
        <p>Give your commands all at once, as opposed to in individual steps.</p>
        <p>The robot can take a while to think of its response, so be patient on startup and when waiting for a reply.</p>
        <button class="btn" name="user_say" onclick="show_task('<?php echo $d;?>', '<?php echo $uid;?>', '<?php echo $action;?>', '<?php echo $patient;?>', '<?php echo $recipient;?>', '<?php echo $source;?>', '<?php echo $goal;?>')">Show next task</button>
      </div>
    </div>

      <?php
  }
}
?>

</div>
</body>

</html>
