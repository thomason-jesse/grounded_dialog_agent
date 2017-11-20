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
// urls the agent uses to communicate with this user
var smsgs_url;
var rmsgs_url;
var amsgs_url;
var smsgur_url;
var omsgur_url;

// Functions that don't access the server or the client-side display.

function draw_alternate_name(name) {
  // TODO: mimic IJCAI'15 nickname/lastname/firstname/etc. name rewrite rules for anonymized people
  return name;
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

// Functions related to manipulating the actual interface and running the task.

// Show an error in the error div.
function show_error(e) {
  $('#err').show();
  $('#err_text').html(e);
}

// Enable the user text input.
function enable_user_text() {
  $('#user_input').prop("disabled", false);
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
    var content = draw_alternate_name(atom);
  } else {
    if (role == "source" || role == "goal") {
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
  }
  $('#' + type + '_' + role + '_panel').html(content);
  $('#' + type + '_' + role + '_panel').prop("hidden", false);
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
  send_agent_string_message(d, uid, m);  // send user string message to the agent
  show_agent_thinking();
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
  send_agent_string_message(d, uid, point);  // send user string message to the agent
  show_agent_thinking();
}

// Write a string message to disk for the server to pick up.
// d - the directory where messages live
// uid - the user id
// m - the string message to write to file
function send_agent_string_message(d, uid, m) {
  var fn = d + uid + ".smsgu.txt";
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
  populate_from_string_or_referent_messages(smsgs_url, rmsgs_url);

  // Check for an action message.
  var contents = get_and_delete_file(amsgs_url);
  if (contents) {
    delete_row_from_dialog_table(-2);  // delete 'thinking'
    var m = process_referent_message(contents);
    $('#action_text').html(m)
    $('#finished_task_div').show();  // show advance to next task button
    disable_user_text();  // just in case
    clearInterval(iv);

    // We need to return early here because the Agent is fast and has likely already booted
    // up the next dialog and sent the greeting message and user request. Instead of eating
    // those here and ending the client-side dialog, we return until this function is set
    // up for polling again.
    return;
  }

  // Check for a request for user messages.
  contents = get_and_delete_file(smsgur_url);
  if (contents) {  // string message request
    delete_row_from_dialog_table(-2);  // delete 'thinking'
    enable_user_text();
  }
  contents = get_and_delete_file(omsgur_url);
  if (contents) {  // oidx message request
    delete_row_from_dialog_table(-2);  // delete 'thinking'
    enable_user_train_object_answer();
  }
}

// Check fo string or referent messages.
function populate_from_string_or_referent_messages(smsgs_url, rmsgs_url) {

  var contents = get_and_delete_file(smsgs_url);
  if (contents) {
    add_row_to_dialog_table(contents, false, -1);
  }

  // Check for a referent message.
  contents = get_and_delete_file(rmsgs_url);
  if (contents) {
    var m = process_referent_message(contents);
    add_row_to_dialog_table(m, false, -1);
  }

}

// Sample a task corresponding to the number and give it to the user.
function show_task(d, uid, action, patient, recipient, source, goal) {
  $('#next_task_div').hide();  // hide next task div
  clear_dialog_table();  // Clear the dialog history.

  // Sample a task of the matching number.
  if (action == 'move') {
    var task_text = "<p>Give the robot a command to solve this problem:<br><span class=\"patient_text\">The object</span> shown below is at the X marked on the <span class=\"source_text\">pink map</span>. The object belongs at the X marked on the <span class=\"goal_text\">green map</span>.</p>";
  } else if (action == 'bring') {
    var task_text = "<p>Give the robot a command to solve this problem:<br><span class=\"recipient_text\">This person</span> needs <span class=\"patient_text\">the object</span> shown below.</p>";
  } else if (action == 'walk') {
    var task_text = "<p>Give the robot a command to solve this problem:<br>The robot should be at the X marked on the <span class=\"goal_text\">green map</span>.</p>";
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
$fold = 0;  # out of 0, 1, 2. Fold 3 is reserved as the test fold always.
$setting = "init";  # either init, train, or test

$d = 'client/';
$active_train_set = get_active_train_set($fold);
shuffle($active_train_set);

# This is a new landing, so we need to set up the task and call the Server to make an instance.
if (!isset($_POST['uid'])) {
  $uid = uniqid();

  # Write a new user file so the Server creates an Agent assigned to this uid.
  $fn = $d . $uid . '.newu.txt';
  write_file($fn, ' ', 'Could not create file to request new dialog agent.');

  # Show instructions.
  $inst = "<p>In this HIT, you will command a robot to perform several tasks. ";
  $inst .= "The robot is learning, and will ask you to reword your commands ";
  $inst .= "and help it better understand concepts. ";
  $inst .= "Use the chat box below to command the robot to complete the given task.</p><br/>";
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

  # Draw a task based on the number.
  # task_roles is a dictionary of roles -> targets for relevant roles.
  $task_roles = draw_task($task_num, $setting);
  $action = $task_roles['action'];
  $patient = (array_key_exists('patient', $task_roles) ? $task_roles['patient'] : false);
  $recipient = (array_key_exists('recipient', $task_roles) ? $task_roles['recipient'] : false);
  $source = (array_key_exists('source', $task_roles) ? $task_roles['source'] : false);
  $goal = (array_key_exists('goal', $task_roles) ? $task_roles['goal'] : false);

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
              <input type="submit" class="btn" value="Okay">
            </form>
        </div>
      </div>
      <div class="col-md-6">
        <div id="nearby_objects_div" hidden>
          <?php
            for ($idx = 0; $idx < count($active_train_set); $idx++) {
              echo "<div class=\"col-md-1 robot_obj_panel\" id=\"robot_obj_" . $idx ."\" onmouseover=\"nearby_objects_highlight('" . $idx . "')\" onmouseleave=\"nearby_objects_clear('" . $idx . "')\">";
              $oidx = explode('_', $active_train_set[$idx])[1];
              echo "<span class=\"va\"></span><img src=\"images/objects/" . $active_train_set[$idx] . ".jpg\" class=\"obj_img\" onclick=\"{nearby_objects_clear_all(); nearby_objects_highlight('" . $idx . "'); send_agent_user_oidx_input('" . $oidx . "', '". $d . "', '" . $uid . "');}\">";
              echo "</div>";
            }
            echo "<div class=\"col-md-1\"><button class=\"btn\" onclick=\"send_agent_user_oidx_input('None', '" . $d . "', '" . $uid . "')\">All / None</button></div>";
          ?>
        </div>
        <div>
          <div class="row">
            <div class="col-md-1 patient_panel" id="interface_patient_panel" hidden></div>
            <div class="col-md-1 recipient_panel" id="interface_recipient_panel" hidden></div>
            <div class="col-md-1 source_panel" id="interface_source_panel" hidden></div>
            <div class="col-md-1 goal_panel" id="interface_goal_panel" hidden></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="row" id="next_task_div">
    <div class="col-md-12">
      <p>Give your commands all at once, as opposed to in individual steps.</p>
      <p>The can take a while to think of its response, so be patient on startup and when waiting for a reply.</p>
      <button class="btn" name="user_say" onclick="show_task('<?php echo $d;?>', '<?php echo $uid;?>', '<?php echo $action;?>', '<?php echo $patient;?>', '<?php echo $recipient;?>', '<?php echo $source;?>', '<?php echo $goal;?>')">Show next task</button>
    </div>
  </div>

    <?php
}

# Show exit instructions.
# TODO: this should be it's own page that the user can navigate to only after finishing the task.
if (false) {
  $uid = $_POST['uid'];
  $mturk_code = $uid."_".substr(sha1("phm_salted_hash".$uid."rwhpidcwha_0"),0,13);
  ?>
  <div class="row">
    <div class="col-md-1"></div>
    <div class="col-md-10">
      <p>
        Thank you for your participation!</p>
      <p>Copy the code below, return to Mechanical Turk, and enter it to receive payment:<br/>
        <?php echo $mturk_code; ?>
      </p>
    </div>
    <div class="col-md-1"></div>
  </div>
  <?php
}
?>

</div>
</body>

</html>
