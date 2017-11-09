<?php

function write_file($fn, $data, $err_msg) {
  $f = fopen($fn, 'w') or die($err_msg);
  fwrite($f, $data);
  fclose($f);
  chmod($fn, "a+rx");
}

?>