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

// Check whether the given url returns a 404.
function url_exists(url)
{
  var http = new XMLHttpRequest();
  http.open('HEAD', url, false);
  http.send();
  return http.status != 404;
}

function get_agent_message(uid)
{
  //Spin until agent message exists, process and delete it when it does.
}

</script>

</head>

<body>
<div id="container">

<?php
require_once('functions.php');

$d = 'client/';

# This is a new landing, so we need to set up the task and call the Server to make an instance.
if (!isset($_POST['uid'])) {
  $uid = uniqid();
  $finished = False;

  # Write a new user file so the Server creates an Agent assigned to this uid.
  $fn = $d . $uid . '.newu.txt';
  write_file($fn, ' ', 'Could not create file to request new dialog agent.');

  # Read initial prompt from agent and start dialog.
}

# Load data from POST.
else {
  # Load other form info.
  $uid = $_POST['uid'];
  $finished = $_POST['finished'];
}

# Do the task.
if (!$finished) {

   # Show instructions.
  $inst = "<p>In this HIT, you will command a robot to perform several tasks. ";
  $inst .= "The robot is learning, and will ask you to reword your commands ";
  $inst .= "and help it better understand concepts. ";
  $inst .= "Use the chat box below to command the robot to complete the given task.</p><br/>";
  ?>
  <div class="row" id="inst_div">
    <div class="col-md-1"></div>
    <div class="col-md-10">
      <?php echo $inst;?>
    </div>
    <div class="col-md-1"></div>
  </div>
    <?php
}

# Show exit instructions.
else {

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
